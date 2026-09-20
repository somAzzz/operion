from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from pydantic import ValidationError

from operion_etl.action_app import (
    ActionApplication,
    ActionCredential,
    create_action_app,
)
from operion_etl.action_models import (
    FOLLOWUP_SIDE_EFFECTS,
    ActionConflict,
    ActionNotFound,
    ActionState,
    Principal,
    ProposalRequest,
    RevisionRequest,
)
from operion_etl.action_store import ActionStore
from operion_etl.action_worker import ActionWorker, FaultPoint, PreflightPolicy

TEST_DSN = os.environ.get("OPERION_TEST_ACTION_DATABASE_URL", "")


class FakeTwentyGateway:
    def __init__(self):
        self.effects: dict[str, dict] = {}
        self.submit_calls = 0

    def preflight(self, action: dict) -> str | None:
        return None

    def submit(self, action: dict) -> dict:
        self.submit_calls += 1
        return self.effects.setdefault(
            action["action_id"],
            {
                "effect_id": action["action_id"],
                "task_id": action["action_id"],
                "task_target_id": f"target-{action['action_id']}",
                "payload_hash": action["payload_hash"],
                "effect_kind": "twenty.followup_task",
            },
        )

    def reconcile(self, action: dict) -> list[dict]:
        effect = self.effects.get(action["action_id"])
        return [effect] if effect else []


@unittest.skipUnless(TEST_DSN, "requires OPERION_TEST_ACTION_DATABASE_URL")
class ActionControlTests(unittest.TestCase):
    def setUp(self):
        migration_store = ActionStore(TEST_DSN)
        with migration_store._connect(privileged=True) as connection:
            connection.execute("DROP SCHEMA public CASCADE")
            connection.execute("CREATE SCHEMA public")
        migration_store.migrate()
        self.store = ActionStore(TEST_DSN, "operion_action_app")
        self.requester = Principal(
            user_id="requester",
            tenant_id="tenant-1",
            companies=frozenset({"AI Demo GmbH"}),
            customer_ids=frozenset({"customer-canonical-1"}),
        )
        self.approver = Principal(
            user_id="approver",
            tenant_id="tenant-1",
            companies=frozenset({"AI Demo GmbH"}),
            customer_ids=frozenset({"customer-canonical-1"}),
            can_approve=True,
        )

    def proposal(
        self,
        key: str,
        *,
        assignee: str = "e3:assignee:valid",
        target_version: str = "v1",
        expires_delta: timedelta = timedelta(hours=1),
        compensates: str | None = None,
    ) -> ProposalRequest:
        return ProposalRequest(
            idempotency_key=key,
            action_type="stub.followup_task",
            target={
                "system": "e3_stub",
                "company": "AI Demo GmbH",
                "customer_id": "customer-1",
                "order_id": f"order-{key}",
            },
            parameters={
                "title": "Investigate fulfillment gap",
                "body": "Review the deterministic shortage evidence.",
                "assignee_id": assignee,
                "due_at": datetime.now(UTC) + timedelta(days=1),
            },
            preconditions={"target_version": target_version},
            side_effects=("internal_stub_record",),
            expires_at=datetime.now(UTC) + expires_delta,
            compensates_action_id=compensates,
        )

    def approved(self, key: str) -> dict:
        action = self.store.propose(self.proposal(key), self.requester)
        return self.store.decide(
            action["action_id"],
            1,
            "approve",
            f"decision-{key}",
            None,
            self.approver,
        )

    def approved_twenty(self, key: str) -> dict:
        proposal = ProposalRequest(
            idempotency_key=key,
            action_type="twenty.followup_task",
            target={
                "system": "twenty",
                "company": "AI Demo GmbH",
                "customer_id": "company-1",
                "order_id": "SO-1",
                "customer_canonical_id": "customer-canonical-1",
                "order_canonical_id": "order-canonical-1",
                "erpnext_customer_id": "ERP-CUSTOMER-1",
            },
            parameters={
                "title": "Review shortfall",
                "body": "Internal follow-up",
                "assignee_id": "member-1",
                "due_at": datetime.now(UTC) + timedelta(days=2),
            },
            preconditions={"target_version": "snapshot-v1"},
            side_effects=FOLLOWUP_SIDE_EFFECTS,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        action = self.store.propose(proposal, self.requester)
        return self.store.decide(
            action["action_id"],
            1,
            "approve",
            f"decision-{key}",
            None,
            self.approver,
        )

    def test_w01_unapproved_and_forged_approval_do_not_execute(self):
        action = self.store.propose(self.proposal("w01"), self.requester)
        self.assertIsNone(self.store.claim("worker"))
        app = ActionApplication(
            self.store,
            [ActionCredential("request-token", "csrf-1", self.requester)],
        )
        client = TestClient(create_action_app(app))
        denied = client.post(
            f"/api/actions/{action['action_id']}/decisions",
            headers={
                "Authorization": "Bearer request-token",
                "X-Operion-CSRF": "csrf-1",
            },
            json={"revision": 1, "decision": "approve", "request_id": "forged"},
        )
        self.assertEqual(403, denied.status_code)
        self.assertEqual([], self.store.stub_effects(action["action_id"]))

    def test_w02_revision_invalidates_old_approval(self):
        action = self.approved("w02")
        original = action["payload_json"]
        revision = RevisionRequest(
            request_id="revise-w02",
            target=original["target"],
            parameters={**original["parameters"], "title": "Changed title"},
            preconditions=original["preconditions"],
            side_effects=tuple(original["side_effects"]),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        revised = self.store.revise(action["action_id"], revision, self.requester)
        self.assertEqual(2, revised["current_revision"])
        self.assertEqual(ActionState.PENDING_APPROVAL.value, revised["state"])
        with self.assertRaises(ActionConflict):
            self.store.decide(
                action["action_id"],
                1,
                "approve",
                "stale-w02",
                None,
                self.approver,
            )

    def test_w03_expiry_revocation_and_cross_tenant_replay(self):
        action = self.approved("w03-revoke")
        revoked = self.store.decide(
            action["action_id"],
            1,
            "revoke",
            "revoke-w03",
            None,
            self.approver,
        )
        self.assertEqual(ActionState.REVOKED.value, revoked["state"])
        expired = self.store.propose(self.proposal("w03-expire"), self.requester)
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE operion_actions SET expires_at = %s WHERE action_id = %s",
                (datetime.now(UTC) - timedelta(seconds=1), expired["action_id"]),
            )
        with self.assertRaises(ActionConflict):
            self.store.decide(
                expired["action_id"],
                1,
                "approve",
                "expired-w03",
                None,
                self.approver,
            )
        outsider = Principal(
            user_id="approver",
            tenant_id="other-tenant",
            companies=frozenset({"AI Demo GmbH"}),
            can_approve=True,
        )
        with self.assertRaises(ActionNotFound):
            self.store.get(action["action_id"], outsider)

    def test_w04_preflight_detects_revoked_owner_and_invalid_assignee(self):
        action = self.approved("w04-owner")
        worker = ActionWorker(
            self.store,
            "worker-w04",
            PreflightPolicy(revoked_owners={"requester"}),
        )
        self.assertEqual("conflict", worker.execute_once()["status"])
        current = self.store.get(action["action_id"], self.requester)
        self.assertEqual(ActionState.CONFLICT.value, current["state"])

    def test_w05_concurrent_proposal_and_workers_have_one_effect(self):
        proposal = self.proposal("w05")
        with ThreadPoolExecutor(max_workers=4) as executor:
            rows = list(
                executor.map(
                    lambda _: self.store.propose(proposal, self.requester), range(4)
                )
            )
        self.assertEqual(1, len({row["action_id"] for row in rows}))
        action = rows[0]
        self.store.decide(
            action["action_id"],
            1,
            "approve",
            "approve-w05",
            None,
            self.approver,
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda index: ActionWorker(
                        self.store, f"worker-{index}"
                    ).execute_once(),
                    range(2),
                )
            )
        self.assertEqual(1, sum(result["status"] == "succeeded" for result in results))
        self.assertEqual(1, len(self.store.stub_effects(action["action_id"])))

    def test_w06_response_loss_enters_unknown_then_reconciles(self):
        action = self.approved("w06")
        worker = ActionWorker(self.store, "worker-w06")
        result = worker.execute_once(FaultPoint.RESPONSE_LOST)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("succeeded", worker.reconcile(action["action_id"])["status"])
        self.assertEqual(1, len(self.store.stub_effects(action["action_id"])))

    def test_w07_w09_crash_and_expired_lease_reconcile_without_reclaim(self):
        action = self.approved("w07")
        first = ActionWorker(self.store, "worker-a")
        result = first.execute_once(FaultPoint.AFTER_REMOTE_COMMIT_CRASH)
        self.assertEqual("crashed", result["status"])
        self.assertEqual(
            "idle", ActionWorker(self.store, "worker-b").execute_once()["status"]
        )
        self.store.expire_lease_for_test(action["action_id"])
        recovered = ActionWorker(self.store, "worker-restart").recover_expired()
        self.assertEqual("succeeded", recovered[0]["status"])
        self.assertEqual(1, len(self.store.stub_effects(action["action_id"])))

    def test_w08_proven_before_send_failure_is_safely_retried(self):
        action = self.approved("w08")
        worker = ActionWorker(self.store, "worker-w08")
        self.assertEqual(
            "safe_retry", worker.execute_once(FaultPoint.BEFORE_SEND)["status"]
        )
        self.assertEqual("succeeded", worker.execute_once()["status"])
        self.assertEqual(1, len(self.store.stub_effects(action["action_id"])))

    def test_w10_changed_target_version_blocks_send(self):
        action = self.approved("w10")
        order_id = action["payload_json"]["target"]["order_id"]
        policy = PreflightPolicy(target_versions={order_id: "v2"})
        result = ActionWorker(self.store, "worker-w10", policy).execute_once()
        self.assertEqual("conflict", result["status"])
        self.assertEqual([], self.store.stub_effects(action["action_id"]))

    def test_w11_pause_and_cancel_do_not_misreport_inflight_action(self):
        action = self.approved("w11-pause")
        self.store.set_pause("global", True, "maintenance", "operator")
        self.assertEqual(
            "idle", ActionWorker(self.store, "worker").execute_once()["status"]
        )
        self.store.set_pause("global", False, "resume", "operator")
        requester_view = self.store.cancel(action["action_id"], self.requester)
        self.assertEqual(ActionState.CANCELLED.value, requester_view["state"])

        inflight = self.approved("w11-inflight")
        ActionWorker(self.store, "worker").execute_once(
            FaultPoint.AFTER_REMOTE_COMMIT_CRASH
        )
        still_inflight = self.store.cancel(inflight["action_id"], self.requester)
        self.assertEqual(ActionState.EXECUTING.value, still_inflight["state"])

        before_send = self.approved("w11-before-send")
        worker = ActionWorker(self.store, "worker-before-send")
        with patch.object(self.store, "is_paused", return_value=True):
            self.assertEqual("paused", worker.execute_once()["status"])
        paused = self.store.get(before_send["action_id"], self.requester)
        self.assertEqual(ActionState.APPROVED.value, paused["state"])
        self.assertEqual([], self.store.stub_effects(before_send["action_id"]))

    def test_w12_strict_schema_and_scope_reject_invalid_input(self):
        payload = self.proposal("w12").model_dump(mode="json")
        payload["unexpected"] = "field"
        with self.assertRaises(ValidationError):
            ProposalRequest.model_validate(payload)
        payload.pop("unexpected")
        payload["parameters"]["assignee_id"] = None
        with self.assertRaises(ValidationError):
            ProposalRequest.model_validate(payload)
        payload["parameters"]["assignee_id"] = "e3:assignee:valid"
        payload["target"]["company"] = "Other Company"
        cross_scope = ProposalRequest.model_validate(payload)
        with self.assertRaises(Exception):
            self.store.propose(cross_scope, self.requester)

        action = self.store.propose(self.proposal("w12-revision"), self.requester)
        current = action["payload_json"]
        with self.assertRaises(ValidationError):
            RevisionRequest(
                request_id="w12-bad-side-effect",
                target=current["target"],
                parameters=current["parameters"],
                preconditions=current["preconditions"],
                side_effects=("send_notification",),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    def test_w13_database_failure_prevents_new_action(self):
        unavailable = ActionStore(
            "postgresql://operion:wrong@127.0.0.1:55432/operion_actions"
        )
        with self.assertRaises(psycopg.OperationalError):
            unavailable.propose(self.proposal("w13"), self.requester)

    def test_w14_multiple_remote_matches_require_manual_review(self):
        action = self.approved("w14")
        worker = ActionWorker(self.store, "worker-w14")
        worker.execute_once(FaultPoint.RESPONSE_LOST)
        self.store.inject_duplicate_stub_effect(
            action["action_id"], action["payload_hash"]
        )
        self.assertEqual(
            "manual_review", worker.reconcile(action["action_id"])["status"]
        )

    def test_w15_success_and_compensation_are_separate_actions(self):
        action = self.approved("w15-original")
        self.assertEqual(
            "succeeded", ActionWorker(self.store, "worker").execute_once()["status"]
        )
        compensation = self.store.propose(
            self.proposal("w15-compensation", compensates=action["action_id"]),
            self.requester,
        )
        self.store.decide(
            compensation["action_id"],
            1,
            "approve",
            "approve-w15-compensation",
            None,
            self.approver,
        )
        self.assertEqual(
            "succeeded", ActionWorker(self.store, "worker").execute_once()["status"]
        )
        original = self.store.get(action["action_id"], self.requester)
        completed_compensation = self.store.get(
            compensation["action_id"], self.requester
        )
        self.assertEqual(ActionState.SUCCEEDED.value, original["state"])
        self.assertEqual(
            action["action_id"], completed_compensation["compensates_action_id"]
        )

    def test_audit_records_are_immutable_and_hash_chained(self):
        action = self.approved("audit")
        ActionWorker(self.store, "worker").execute_once()
        self.assertTrue(self.store.verify_event_chain(action["action_id"]))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.store._connect() as connection:
                connection.execute(
                    "UPDATE operion_action_events SET event_type = 'CHANGED' "
                    "WHERE action_id = %s",
                    (action["action_id"],),
                )

    def test_e4_response_loss_reconciles_same_twenty_task(self):
        action = self.approved_twenty("e4-response-loss")
        gateway = FakeTwentyGateway()
        worker = ActionWorker(self.store, "e4-worker", twenty_gateway=gateway)
        result = worker.execute_once(FaultPoint.RESPONSE_LOST)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("succeeded", worker.reconcile(action["action_id"])["status"])
        self.assertEqual(1, gateway.submit_calls)
        completed = self.store.get(action["action_id"], self.requester)
        self.assertEqual(ActionState.SUCCEEDED.value, completed["state"])
        self.assertEqual(action["action_id"], completed["remote_ref"])

    def test_e4_verified_proposal_cannot_be_retargeted_by_revision(self):
        action = self.approved_twenty("e4-no-client-retarget")
        payload = action["payload_json"]
        revision = RevisionRequest(
            request_id="e4-forged-revision",
            target=payload["target"],
            parameters={**payload["parameters"], "title": "Changed by client"},
            preconditions=payload["preconditions"],
            side_effects=tuple(payload["side_effects"]),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        with self.assertRaises(ActionConflict):
            self.store.revise(action["action_id"], revision, self.requester)
        other_customer = Principal(
            user_id="other-customer-user",
            tenant_id="tenant-1",
            companies=frozenset({"AI Demo GmbH"}),
            customer_ids=frozenset({"other-customer"}),
        )
        self.assertEqual([], self.store.list(other_customer))
        with self.assertRaises(ActionNotFound):
            self.store.get(action["action_id"], other_customer)


if __name__ == "__main__":
    unittest.main()
