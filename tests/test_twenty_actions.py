from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from operion_etl.action_store import content_hash
from operion_etl.twenty_actions import (
    TwentyActionMismatch,
    TwentyFollowupGateway,
    followup_target_id,
)


class FakeTwenty:
    def __init__(self) -> None:
        self.company = {
            "id": "company-1",
            "updatedAt": "2026-09-20T12:00:00Z",
            "deletedAt": None,
            "wwiExternalId": "customer-canonical-1",
        }
        self.member = {
            "id": "member-1",
            "updatedAt": "2026-09-20T12:00:00Z",
            "deletedAt": None,
            "userId": "user-1",
        }
        self.tasks: dict[str, dict] = {}
        self.targets: dict[str, dict] = {}
        self.create_task_calls = 0
        self.create_target_calls = 0

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        variables = variables or {}
        if "FollowupPreflight" in query:
            return {"company": self.company, "workspaceMember": self.member}
        if "query FollowupTask" in query:
            row = self.tasks.get(variables["id"])
            return {
                "tasks": {
                    "totalCount": int(row is not None),
                    "edges": [{"node": row}] if row else [],
                }
            }
        if "query FollowupTarget" in query:
            row = self.targets.get(variables["id"])
            return {
                "taskTargets": {
                    "totalCount": int(row is not None),
                    "edges": [{"node": row}] if row else [],
                }
            }
        if "CreateFollowupTarget" in query:
            self.create_target_calls += 1
            data = variables["data"]
            self.targets[data["id"]] = {**data, "deletedAt": None}
            return {"createTaskTarget": {"id": data["id"]}}
        if "CreateFollowup" in query:
            self.create_task_calls += 1
            data = variables["data"]
            self.tasks[data["id"]] = {
                **data,
                "bodyV2": data["bodyV2"],
                "deletedAt": None,
            }
            return {"createTask": {"id": data["id"]}}
        raise AssertionError(f"unexpected query: {query}")


class FakeERPNext:
    def __init__(self) -> None:
        self.order = {
            "name": "SO-1",
            "modified": "2026-09-20 12:00:00.000000",
            "customer": "ERP-CUSTOMER-1",
            "docstatus": 1,
            "status": "To Deliver and Bill",
        }

    def record(self, doctype: str, name: str) -> dict:
        if doctype != "Sales Order" or name != self.order["name"]:
            raise RuntimeError("record not found")
        return self.order.copy()


class TwentyFollowupGatewayTests(unittest.TestCase):
    def setUp(self):
        self.twenty = FakeTwenty()
        self.erpnext = FakeERPNext()
        self.gateway = TwentyFollowupGateway(self.twenty, self.erpnext)
        self.action_id = str(uuid4())
        self.target = {
            "system": "twenty",
            "company": "AI Demo GmbH",
            "customer_id": "company-1",
            "order_id": "SO-1",
            "customer_canonical_id": "customer-canonical-1",
            "order_canonical_id": "order-canonical-1",
            "erpnext_customer_id": "ERP-CUSTOMER-1",
        }
        version = self.gateway.current_snapshot(self.target, "member-1")
        payload = {
            "target": self.target,
            "parameters": {
                "title": "Review shortfall",
                "body": "Internal details",
                "assignee_id": "member-1",
                "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
            "preconditions": {"target_version": version},
        }
        self.action = {
            "action_id": self.action_id,
            "action_type": "twenty.followup_task",
            "payload_json": payload,
            "payload_hash": content_hash(payload),
            "owner_id": "requester",
        }

    def test_submit_uses_deterministic_ids_without_repeat_mutations(self):
        first = self.gateway.submit(self.action)
        second = self.gateway.submit(self.action)
        self.assertEqual(self.action_id, first["task_id"])
        self.assertEqual(first, second)
        self.assertEqual(1, self.twenty.create_task_calls)
        self.assertEqual(1, self.twenty.create_target_calls)
        self.assertEqual(followup_target_id(self.action_id), first["task_target_id"])

    def test_reconcile_repairs_only_the_missing_deterministic_target(self):
        parameters = self.action["payload_json"]["parameters"]
        self.twenty.tasks[self.action_id] = {
            "id": self.action_id,
            "title": parameters["title"],
            "bodyV2": {"markdown": parameters["body"]},
            "dueAt": parameters["due_at"],
            "status": "TODO",
            "assigneeId": parameters["assignee_id"],
            "deletedAt": None,
        }
        effects = self.gateway.reconcile(self.action)
        self.assertEqual(1, len(effects))
        self.assertEqual(0, self.twenty.create_task_calls)
        self.assertEqual(1, self.twenty.create_target_calls)

    def test_existing_deterministic_id_with_other_content_is_manual_review(self):
        self.twenty.tasks[self.action_id] = {
            "id": self.action_id,
            "title": "Different content",
            "bodyV2": {"markdown": "Different content"},
            "dueAt": datetime.now(UTC).isoformat(),
            "status": "TODO",
            "assigneeId": "member-1",
            "deletedAt": None,
        }
        with self.assertRaises(TwentyActionMismatch):
            self.gateway.submit(self.action)
        self.assertEqual(0, self.twenty.create_task_calls)

    def test_preflight_detects_version_and_identity_changes(self):
        self.assertIsNone(self.gateway.preflight(self.action))
        self.erpnext.order["modified"] = "2026-09-20 12:01:00.000000"
        self.assertEqual("TARGET_VERSION_CHANGED", self.gateway.preflight(self.action))
        self.erpnext.order["customer"] = "OTHER-CUSTOMER"
        self.assertEqual(
            "TARGET_ORDER_CUSTOMER_CHANGED", self.gateway.preflight(self.action)
        )


if __name__ == "__main__":
    unittest.main()
