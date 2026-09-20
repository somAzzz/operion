from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from operion_etl.action_app import (
    ActionApplication,
    ActionCredential,
    create_action_app,
)
from operion_etl.action_models import Principal
from operion_etl.action_store import ActionStore

TEST_DSN = os.environ.get("OPERION_TEST_ACTION_DATABASE_URL", "")


@unittest.skipUnless(TEST_DSN, "requires OPERION_TEST_ACTION_DATABASE_URL")
class ActionAppTests(unittest.TestCase):
    def setUp(self):
        migration_store = ActionStore(TEST_DSN)
        with migration_store._connect(privileged=True) as connection:
            connection.execute("DROP SCHEMA public CASCADE")
            connection.execute("CREATE SCHEMA public")
        migration_store.migrate()
        self.store = ActionStore(TEST_DSN, "operion_action_app")
        requester = Principal(
            user_id="requester",
            tenant_id="tenant-1",
            companies=frozenset({"AI Demo GmbH"}),
        )
        approver = Principal(
            user_id="approver",
            tenant_id="tenant-1",
            companies=frozenset({"AI Demo GmbH"}),
            can_approve=True,
        )
        outsider = Principal(
            user_id="outsider",
            tenant_id="tenant-2",
            companies=frozenset({"AI Demo GmbH"}),
            can_approve=True,
        )
        application = ActionApplication(
            self.store,
            [
                ActionCredential("request-token", "request-csrf", requester),
                ActionCredential("approve-token", "approve-csrf", approver),
                ActionCredential("outside-token", "outside-csrf", outsider),
            ],
        )
        self.client = TestClient(create_action_app(application))
        self.request_headers = {
            "Authorization": "Bearer request-token",
            "X-Operion-CSRF": "request-csrf",
        }
        self.approve_headers = {
            "Authorization": "Bearer approve-token",
            "X-Operion-CSRF": "approve-csrf",
        }

    def proposal(self) -> dict:
        return {
            "idempotency_key": "api-proposal-1",
            "action_type": "stub.followup_task",
            "target": {
                "system": "e3_stub",
                "company": "AI Demo GmbH",
                "customer_id": "customer-1",
                "order_id": "order-1",
            },
            "parameters": {
                "title": "Review shortage",
                "body": "Inspect deterministic evidence.",
                "assignee_id": "e3:assignee:valid",
                "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
            "preconditions": {"target_version": "v1"},
            "side_effects": ["internal_stub_record"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }

    def test_mutations_require_csrf_and_strict_schema(self):
        missing_csrf = self.client.post(
            "/api/action-proposals",
            headers={"Authorization": "Bearer request-token"},
            json=self.proposal(),
        )
        self.assertEqual(403, missing_csrf.status_code)
        invalid = self.proposal()
        invalid["approved_by"] = "client-forged"
        response = self.client.post(
            "/api/action-proposals", headers=self.request_headers, json=invalid
        )
        self.assertEqual(422, response.status_code)

    def test_decision_uses_server_payload_and_is_idempotent(self):
        created = self.client.post(
            "/api/action-proposals",
            headers=self.request_headers,
            json=self.proposal(),
        ).json()
        decision = {
            "revision": 1,
            "decision": "approve",
            "request_id": "api-decision-1",
        }
        first = self.client.post(
            f"/api/actions/{created['action_id']}/decisions",
            headers=self.approve_headers,
            json=decision,
        )
        second = self.client.post(
            f"/api/actions/{created['action_id']}/decisions",
            headers=self.approve_headers,
            json=decision,
        )
        self.assertEqual(200, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertEqual("APPROVED", second.json()["state"])

    def test_cross_tenant_lookup_does_not_disclose_action(self):
        created = self.client.post(
            "/api/action-proposals",
            headers=self.request_headers,
            json=self.proposal(),
        ).json()
        response = self.client.get(
            f"/api/actions/{created['action_id']}",
            headers={"Authorization": "Bearer outside-token"},
        )
        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
