from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .action_models import ActionState
from .action_store import ActionStore


class FaultPoint(StrEnum):
    NONE = "none"
    BEFORE_SEND = "before_send"
    RESPONSE_LOST = "response_lost"
    AFTER_REMOTE_COMMIT_CRASH = "after_remote_commit_crash"
    BEFORE_SUCCESS_PERSIST = "before_success_persist"


@dataclass
class PreflightPolicy:
    companies: frozenset[str] = frozenset({"AI Demo GmbH"})
    assignees: frozenset[str] = frozenset({"e3:assignee:valid"})
    target_versions: dict[str, str] = field(default_factory=dict)
    revoked_owners: set[str] = field(default_factory=set)

    def validate(self, action: dict[str, Any]) -> str | None:
        payload = action["payload_json"]
        target = payload["target"]
        parameters = payload["parameters"]
        preconditions = payload["preconditions"]
        if action["owner_id"] in self.revoked_owners:
            return "OWNER_PERMISSION_REVOKED"
        if target["company"] not in self.companies:
            return "COMPANY_SCOPE_CHANGED"
        if parameters["assignee_id"] not in self.assignees:
            return "ASSIGNEE_INVALID"
        current_version = self.target_versions.get(
            target["order_id"], preconditions["target_version"]
        )
        if current_version != preconditions["target_version"]:
            return "TARGET_VERSION_CHANGED"
        return None


class ActionWorker:
    def __init__(
        self,
        store: ActionStore,
        worker_id: str,
        policy: PreflightPolicy | None = None,
    ) -> None:
        self.store = store
        self.worker_id = worker_id
        self.policy = policy or PreflightPolicy()

    def execute_once(self, fault: FaultPoint = FaultPoint.NONE) -> dict[str, Any]:
        action = self.store.claim(self.worker_id)
        if action is None:
            return {"status": "idle"}
        action_id = action["action_id"]
        attempt_id = action["attempt_id"]
        lease_token = action["lease_token"]
        preflight_error = self.policy.validate(action)
        if preflight_error:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.CONFLICT,
                event_type="PREFLIGHT_CONFLICT",
                actor=self.worker_id,
                error_code=preflight_error,
            )
            return {"status": "conflict", "action_id": action_id}
        if self.store.is_paused(action["action_type"]):
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.APPROVED,
                event_type="PAUSED_BEFORE_SEND",
                actor=self.worker_id,
            )
            return {"status": "paused", "action_id": action_id}
        if fault == FaultPoint.BEFORE_SEND:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.APPROVED,
                event_type="SAFE_RETRY_CONFIRMED_NO_SUBMIT",
                actor=self.worker_id,
                error_code="INJECTED_BEFORE_SEND",
            )
            return {"status": "safe_retry", "action_id": action_id}

        effect = self.store.stub_submit(action_id, action["payload_hash"])
        remote_ref = effect["effect_id"]
        if fault == FaultPoint.RESPONSE_LOST:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.UNKNOWN,
                event_type="RESULT_UNKNOWN",
                actor=self.worker_id,
                remote_ref=remote_ref,
                error_code="INJECTED_RESPONSE_LOSS",
            )
            return {"status": "unknown", "action_id": action_id}
        if fault in {
            FaultPoint.AFTER_REMOTE_COMMIT_CRASH,
            FaultPoint.BEFORE_SUCCESS_PERSIST,
        }:
            return {
                "status": "crashed",
                "action_id": action_id,
                "fault": fault.value,
            }

        self.store.transition_attempt(
            action_id,
            attempt_id,
            lease_token,
            state=ActionState.SUCCEEDED,
            event_type="SUCCEEDED_AFTER_READBACK",
            actor=self.worker_id,
            remote_ref=remote_ref,
            result={"effect_id": remote_ref, "payload_hash": effect["payload_hash"]},
        )
        return {"status": "succeeded", "action_id": action_id}

    def reconcile(self, action_id: str) -> dict[str, Any]:
        action = self.store.mark_reconciling(action_id, self.worker_id)
        effects = self.store.stub_effects(action_id)
        attempt_id = self._latest_attempt(action_id)
        lease_token = action["lease_token"]
        if not attempt_id or not lease_token:
            raise RuntimeError("reconciling action has no recoverable lease evidence")
        if len(effects) == 0:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.APPROVED,
                event_type="RECONCILED_NO_SUBMIT_SAFE_RETRY",
                actor=self.worker_id,
            )
            return {"status": "safe_retry", "action_id": action_id}
        if len(effects) > 1:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.MANUAL_REVIEW,
                event_type="RECONCILIATION_AMBIGUOUS",
                actor=self.worker_id,
                error_code="MULTIPLE_REMOTE_RESULTS",
            )
            return {"status": "manual_review", "action_id": action_id}
        effect = effects[0]
        if effect["payload_hash"] != action["payload_hash"]:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.MANUAL_REVIEW,
                event_type="RECONCILIATION_MISMATCH",
                actor=self.worker_id,
                remote_ref=effect["effect_id"],
                error_code="REMOTE_CONTENT_MISMATCH",
            )
            return {"status": "manual_review", "action_id": action_id}
        self.store.transition_attempt(
            action_id,
            attempt_id,
            lease_token,
            state=ActionState.SUCCEEDED,
            event_type="RECONCILED_SUCCEEDED",
            actor=self.worker_id,
            remote_ref=effect["effect_id"],
            result={
                "effect_id": effect["effect_id"],
                "payload_hash": effect["payload_hash"],
            },
        )
        return {"status": "succeeded", "action_id": action_id}

    def recover_expired(self) -> list[dict[str, Any]]:
        return [
            self.reconcile(action_id)
            for action_id in self.store.recover_expired_leases(self.worker_id)
        ]

    def _latest_attempt(self, action_id: str) -> str | None:
        with self.store._connect() as connection:
            row = connection.execute(
                """
                SELECT attempt_id FROM operion_action_attempts
                WHERE action_id = %s ORDER BY created_at DESC LIMIT 1
                """,
                (action_id,),
            ).fetchone()
            return row["attempt_id"] if row else None


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-action-worker")
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--worker-id", default="operion-e3-worker")
    args = parser.parse_args()
    dsn = os.environ.get("OPERION_ACTION_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPERION_ACTION_DATABASE_URL is required")
    worker = ActionWorker(
        ActionStore(
            dsn,
            os.environ.get("OPERION_ACTION_DATABASE_ROLE") or None,
        ),
        args.worker_id,
    )
    result = worker.recover_expired() if args.recover else worker.execute_once()
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
