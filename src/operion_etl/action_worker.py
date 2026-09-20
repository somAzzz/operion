from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .action_models import ActionState
from .action_store import ActionStore
from .identity_readback import ERPNextReadClient
from .twenty import TwentyClient, read_env
from .twenty_actions import (
    TwentyActionMismatch,
    TwentyActionUnavailable,
    TwentyFollowupGateway,
)


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
        if action["action_type"] == "stub.followup_task":
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
        twenty_gateway: TwentyFollowupGateway | None = None,
    ) -> None:
        self.store = store
        self.worker_id = worker_id
        self.policy = policy or PreflightPolicy()
        self.twenty_gateway = twenty_gateway

    def _preflight(self, action: dict[str, Any]) -> str | None:
        error = self.policy.validate(action)
        if error or action["action_type"] == "stub.followup_task":
            return error
        if action["action_type"] == "twenty.followup_task":
            if self.twenty_gateway is None:
                return "EXECUTOR_UNAVAILABLE"
            return self.twenty_gateway.preflight(action)
        return "UNSUPPORTED_ACTION_TYPE"

    def _submit(self, action: dict[str, Any]) -> dict[str, Any]:
        if action["action_type"] == "stub.followup_task":
            return self.store.stub_submit(action["action_id"], action["payload_hash"])
        if action["action_type"] == "twenty.followup_task" and self.twenty_gateway:
            return self.twenty_gateway.submit(action)
        raise TwentyActionMismatch("UNSUPPORTED_ACTION_TYPE")

    def _reconcile_effects(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        if action["action_type"] == "stub.followup_task":
            return self.store.stub_effects(action["action_id"])
        if action["action_type"] == "twenty.followup_task" and self.twenty_gateway:
            return self.twenty_gateway.reconcile(action)
        raise TwentyActionMismatch("UNSUPPORTED_ACTION_TYPE")

    @staticmethod
    def _json_result(effect: dict[str, Any]) -> dict[str, Any]:
        """Normalize gateway evidence before it is persisted to JSONB."""
        return json.loads(json.dumps(effect, default=str))

    def _outcome(
        self, status: str, action_id: str | None = None, **details: Any
    ) -> dict[str, Any]:
        self.store.worker_heartbeat(
            self.worker_id,
            status,
            action_id if status == "crashed" else None,
            os.environ.get("OPERION_RELEASE_ID") or None,
        )
        return {
            "status": status,
            **({"action_id": action_id} if action_id else {}),
            **details,
        }

    def execute_once(self, fault: FaultPoint = FaultPoint.NONE) -> dict[str, Any]:
        release_id = os.environ.get("OPERION_RELEASE_ID") or None
        self.store.worker_heartbeat(self.worker_id, "polling", release_id=release_id)
        action = self.store.claim(self.worker_id)
        if action is None:
            self.store.worker_heartbeat(self.worker_id, "idle", release_id=release_id)
            return {"status": "idle"}
        action_id = action["action_id"]
        attempt_id = action["attempt_id"]
        lease_token = action["lease_token"]
        self.store.worker_heartbeat(self.worker_id, "executing", action_id, release_id)
        try:
            preflight_error = self._preflight(action)
        except TwentyActionUnavailable:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.APPROVED,
                event_type="PREFLIGHT_UNAVAILABLE_SAFE_RETRY",
                actor=self.worker_id,
                error_code="PREFLIGHT_SOURCE_UNAVAILABLE",
            )
            return self._outcome("safe_retry", action_id)
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
            return self._outcome("conflict", action_id)
        if self.store.is_paused(action["action_type"]):
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.APPROVED,
                event_type="PAUSED_BEFORE_SEND",
                actor=self.worker_id,
            )
            return self._outcome("paused", action_id)
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
            return self._outcome("safe_retry", action_id)

        try:
            effect = self._submit(action)
        except TwentyActionMismatch as error:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.MANUAL_REVIEW,
                event_type="REMOTE_CONTENT_MISMATCH",
                actor=self.worker_id,
                error_code=str(error),
            )
            return self._outcome("manual_review", action_id)
        except TwentyActionUnavailable:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.UNKNOWN,
                event_type="RESULT_UNKNOWN",
                actor=self.worker_id,
                error_code="TWENTY_RESULT_UNKNOWN",
            )
            return self._outcome("unknown", action_id)
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
            return self._outcome("unknown", action_id)
        if fault in {
            FaultPoint.AFTER_REMOTE_COMMIT_CRASH,
            FaultPoint.BEFORE_SUCCESS_PERSIST,
        }:
            return self._outcome("crashed", action_id, fault=fault.value)

        self.store.transition_attempt(
            action_id,
            attempt_id,
            lease_token,
            state=ActionState.SUCCEEDED,
            event_type="SUCCEEDED_AFTER_READBACK",
            actor=self.worker_id,
            remote_ref=remote_ref,
            result=self._json_result(effect),
        )
        return self._outcome("succeeded", action_id)

    def reconcile(self, action_id: str) -> dict[str, Any]:
        self.store.worker_heartbeat(
            self.worker_id,
            "reconciling",
            action_id,
            os.environ.get("OPERION_RELEASE_ID") or None,
        )
        action = self.store.mark_reconciling(action_id, self.worker_id)
        attempt_id = self._latest_attempt(action_id)
        lease_token = action["lease_token"]
        if not attempt_id or not lease_token:
            raise RuntimeError("reconciling action has no recoverable lease evidence")
        try:
            effects = self._reconcile_effects(action)
        except TwentyActionMismatch as error:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.MANUAL_REVIEW,
                event_type="RECONCILIATION_MISMATCH",
                actor=self.worker_id,
                error_code=str(error),
            )
            return self._outcome("manual_review", action_id)
        except TwentyActionUnavailable:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.RECONCILING,
                event_type="RECONCILIATION_DEFERRED",
                actor=self.worker_id,
                error_code="TWENTY_UNAVAILABLE",
            )
            return self._outcome("reconciling", action_id)
        if len(effects) == 0:
            self.store.transition_attempt(
                action_id,
                attempt_id,
                lease_token,
                state=ActionState.APPROVED,
                event_type="RECONCILED_NO_SUBMIT_SAFE_RETRY",
                actor=self.worker_id,
            )
            return self._outcome("safe_retry", action_id)
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
            return self._outcome("manual_review", action_id)
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
            return self._outcome("manual_review", action_id)
        self.store.transition_attempt(
            action_id,
            attempt_id,
            lease_token,
            state=ActionState.SUCCEEDED,
            event_type="RECONCILED_SUCCEEDED",
            actor=self.worker_id,
            remote_ref=effect["effect_id"],
            result=self._json_result(effect),
        )
        return self._outcome("succeeded", action_id)

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
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--recover", action="store_true")
    mode.add_argument("--reconcile", metavar="ACTION_ID")
    parser.add_argument("--worker-id", default="operion-e3-worker")
    args = parser.parse_args()
    if os.environ.get("OPERION_ENVIRONMENT") == "enterprise":
        if os.environ.get("OPERION_WRITES_ENABLED") != "1":
            raise SystemExit("enterprise write release gate is closed")
        if not os.environ.get("OPERION_RELEASE_ID", "").strip():
            raise SystemExit("OPERION_RELEASE_ID is required for enterprise writes")
    dsn = os.environ.get("OPERION_ACTION_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPERION_ACTION_DATABASE_URL is required")
    values = {
        **read_env(Path(os.environ.get("OPERION_ENV_FILE", ".env"))),
        **os.environ,
    }
    twenty_gateway = None
    twenty_key = values.get("TWENTY_API_KEY", "")
    erpnext_key = values.get("ERPNEXT_API_KEY_READ_ONLY", "")
    if twenty_key and erpnext_key:
        twenty_gateway = TwentyFollowupGateway(
            TwentyClient(
                values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
                twenty_key,
            ),
            ERPNextReadClient(
                values.get("ERPNEXT_API_BASE_URL", "http://localhost:8080"),
                erpnext_key,
            ),
        )
    worker = ActionWorker(
        ActionStore(
            dsn,
            os.environ.get("OPERION_ACTION_DATABASE_ROLE") or None,
        ),
        args.worker_id,
        twenty_gateway=twenty_gateway,
    )
    if args.reconcile:
        result = worker.reconcile(args.reconcile)
    else:
        result = worker.recover_expired() if args.recover else worker.execute_once()
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
