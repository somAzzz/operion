import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from operion_etl.agent_runtime import AgentDependencies, get_order_delivery_evidence
from operion_etl.answer_evidence import AnswerPlan, EvidenceError, TableSelection
from operion_etl.mcp_server import create_server
from operion_etl.read_tools import AccessScope, CanonicalRepository, ScopeDeniedError

DATA = Path("data/canonical/interview-wwi-v1")
SCOPE = AccessScope(
    "AI Demo GmbH", frozenset(f"wwi:organization:customer:{i}" for i in (65, 935))
)


class DeliveryTestHelpers:
    def deps(self, question):
        return AgentDependencies(self.repo, SCOPE, "operator", user_request=question)

    def query(self, deps, order):
        return get_order_delivery_evidence(SimpleNamespace(deps=deps), order)

    def plan(self, result, *facts):
        return AnswerPlan(
            language="en",
            facts=list(facts),
            tables=[
                TableSelection(table_id=result["answer_evidence"]["tables"][0]["id"])
            ],
        )


class SnapshotDeliveryCases(DeliveryTestHelpers):
    def test_T01_confirmed_after_expected_not_line_receipt(self):
        deps = self.deps(
            "Order 66823: customer reports nothing on the 18th. Did all 48 arrive?"
        )
        result = self.query(deps, "66823")
        data = result["data"]
        self.assertEqual(64067, data["invoices"][0]["invoice_id"])
        self.assertEqual(1, data["invoices"][0]["calendar_days_from_expected"])
        answer = deps.evidence.render(self.plan(result))
        for text in (
            "User statement / request",
            "2016-02-18",
            "2016-02-19T07:25:00",
            "ordered 48",
            "picked 48",
            "Not established: actual arrival",
            "Next: verify",
            "Historical WWI snapshot",
        ):
            self.assertIn(text, answer)
        actual = asyncio.run(
            create_server(self.repo, SCOPE).call_tool(
                "get_order_delivery_evidence", {"order_id": "66823"}
            )
        )
        self.assertEqual(data, actual.structured_content)

    def test_T02_complete_empty_is_not_non_delivery(self):
        deps = self.deps("Order 73279")
        result = self.query(deps, "73279")
        self.assertEqual("no_linked_invoice", result["data"]["lookup"])
        self.assertIn(
            "No linked invoice in this WWI slice",
            deps.evidence.render(self.plan(result)),
        )

    def test_T03_tool_must_not_choose_an_unbound_subject(self):
        for question in (
            "Is 66823 late?",
            "Did it arrive?",
            "Order number 66823: was receipt confirmed?",
        ):
            deps = self.deps(question)
            foreign = self.query(deps, "31349")
            with self.subTest(question=question), self.assertRaises(EvidenceError):
                deps.evidence.render(self.plan(foreign))

    def test_T03_other_orders_failure_cannot_appear_in_valid_card(self):
        deps = self.deps("Order 66823")
        target = self.query(deps, "66823")
        self.query(deps, "99999")
        with self.assertRaisesRegex(EvidenceError, "DELIVERY_ORDER_MISMATCH"):
            deps.evidence.render(self.plan(target))

    def test_T03_bare_target_and_labelled_alternative(self):
        deps = self.deps(
            "Look up 66823; can an invoice for order 31349 serve as evidence?"
        )
        other = self.query(deps, "31349")
        with self.assertRaises(EvidenceError):
            deps.evidence.render(self.plan(other))

    def test_T03_invoice_identity_cannot_be_reused_across_order_buckets(self):
        path = self.fixture()
        snapshot = json.loads(path.read_text())
        snapshot["orders"]["wwi:sales_order:66823"]["invoices"][0]["invoice_id"] = 33513
        path.write_text(json.dumps(snapshot))
        result = self.query(self.deps("Order 66823"), "66823")
        self.assertFalse(result["ok"])

    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name) / DATA.name
        shutil.copytree(DATA, directory)
        self.repo = CanonicalRepository(directory)
        return directory / "delivery-evidence-v1.json"

    def test_T04_same_day_and_early_confirmation_are_not_late(self):
        path = self.fixture()
        snapshot = json.loads(path.read_text())
        invoice = snapshot["orders"]["wwi:sales_order:66823"]["invoices"][0]
        for ts, days, phrase in (
            ("2016-02-18T23:59:59", 0, "on expected date"),
            ("2016-02-17T07:15:00", -1, "before expected date"),
        ):
            invoice["confirmed_at"] = ts
            path.write_text(json.dumps(snapshot))
            deps = self.deps("Order 66823")
            result = self.query(deps, "66823")
            self.assertEqual(
                days, result["data"]["invoices"][0]["calendar_days_from_expected"]
            )
            self.assertIn(phrase, deps.evidence.render(self.plan(result)))

    def test_T05_source_failure_cannot_mint_absence(self):
        path = self.fixture()
        path.unlink()
        deps = self.deps("Order 66823")
        failed = self.query(deps, "66823")
        self.assertEqual("source_unavailable", failed["error"]["code"])
        self.assertFalse(failed["answer_evidence"]["tables"])
        answer = deps.evidence.render(AnswerPlan(language="en"))
        self.assertNotIn("No linked invoice", answer)
        self.assertNotIn("64067", answer)

    def test_multiple_documents_credit_and_missing_timestamp(self):
        path = self.fixture()
        snapshot = json.loads(path.read_text())
        invoices = snapshot["orders"]["wwi:sales_order:66823"]["invoices"]
        snapshot["orders"]["wwi:sales_order:66823"]["linked_invoice_count"] = 3
        invoices.extend(
            [
                dict(invoices[0], invoice_id=2, credit_note=True),
                dict(invoices[0], invoice_id=3, confirmed_at=None),
            ]
        )
        path.write_text(json.dumps(snapshot))
        data = self.repo.get_order_delivery_evidence("66823", SCOPE)
        self.assertEqual(
            [1, None, None],
            [i["calendar_days_from_expected"] for i in data["invoices"]],
        )
        self.assertEqual("linked_invoices", data["lookup"])

    def test_incomplete_coverage_and_bad_relationship_fail_closed(self):
        path = self.fixture()
        snapshot = json.loads(path.read_text())
        key = "wwi:sales_order:66823"
        snapshot["orders"][key]["invoices"][0]["invoice_order_id"] = 31349
        for mode in ("broken", "missing"):
            if mode == "missing":
                del snapshot["orders"][key]
            path.write_text(json.dumps(snapshot))
            self.assertEqual(
                "source_unavailable",
                self.query(self.deps("Order 66823"), "66823")["error"]["code"],
            )
        with self.assertRaises(ScopeDeniedError):
            self.repo.get_order_delivery_evidence(
                "66823", AccessScope("AI Demo GmbH", frozenset())
            )


class DeliveryScopeCases(DeliveryTestHelpers):
    def test_T03_repeated_wrong_invoice_is_blocked_at_publication(self):
        from fastapi.testclient import TestClient
        from pydantic_ai.messages import ToolReturnPart
        from pydantic_ai.models.function import DeltaToolCall, FunctionModel

        from operion_etl.agent_app import AgentApplication, create_app
        from operion_etl.agent_runtime import AgentSettings, create_operion_agent
        from operion_etl.session_store import ConversationStore

        attempts = []

        async def wrong_model(messages, info):
            returns = [
                p.content
                for m in messages
                for p in m.parts
                if isinstance(p, ToolReturnPart)
                and p.tool_name == "get_order_delivery_evidence"
            ]
            if not returns:
                yield {
                    n: DeltaToolCall(
                        name="get_order_delivery_evidence",
                        json_args=json.dumps({"order_id": order}),
                        tool_call_id=f"read-{order}",
                    )
                    for n, order in enumerate(("66823", "31349"))
                }
                return
            manifests = {r["data"]["order_id"]: r["answer_evidence"] for r in returns}
            foreign = manifests["wwi:sales_order:31349"]["facts"][0]
            attempts.append(foreign["value"])
            yield {
                0: DeltaToolCall(
                    name="present_answer",
                    tool_call_id=f"wrong-{len(attempts)}",
                    json_args=json.dumps(
                        {
                            "plan": {
                                "language": "en",
                                "facts": [foreign["id"]],
                                "tables": [
                                    {
                                        "table_id": manifests["wwi:sales_order:66823"][
                                            "tables"
                                        ][0]["id"]
                                    }
                                ],
                            }
                        }
                    ),
                )
            }

        with tempfile.TemporaryDirectory() as temp:
            store = ConversationStore(Path(temp) / "session.db")
            settings = AgentSettings()
            app = AgentApplication(
                settings=settings,
                repository=self.repo,
                scope=SCOPE,
                store=store,
                token="test-delivery",
                user_id="tester",
                agent=create_operion_agent(
                    settings, model=FunctionModel(stream_function=wrong_model)
                ),
            )
            with TestClient(create_app(app)) as client:
                response = client.post(
                    "/api/agent",
                    headers={
                        "Authorization": "Bearer test-delivery",
                        "Accept": "text/event-stream",
                    },
                    json={
                        "threadId": "case",
                        "runId": "bad-invoice",
                        "state": {},
                        "context": [],
                        "forwardedProps": {},
                        "tools": [],
                        "messages": [
                            {
                                "id": "question",
                                "role": "user",
                                "content": "Investigate order 66823.",
                            }
                        ],
                    },
                )
            events = [
                json.loads(line[6:])
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            self.assertEqual([33513, 33513], attempts)
            self.assertEqual("RUN_ERROR", events[-1]["type"])
            self.assertFalse(any(e["type"] == "TEXT_MESSAGE_CONTENT" for e in events))
            self.assertEqual(
                "DELIVERY_ORDER_MISMATCH",
                store.run("bad-invoice", "tester")["error_code"],
            )
            self.assertFalse(store.history("case", "tester"))

    def test_T03_current_authorized_same_customer_wrong_invoice(self):
        deps = self.deps("Order 66823: investigate the delivery dispute.")
        other = self.query(deps, "31349")
        target = self.query(deps, "66823")
        self.assertEqual(other["data"]["customer_id"], target["data"]["customer_id"])
        valid = other["answer_evidence"]["facts"][0]
        self.assertEqual(33513, valid["value"])
        for bad in (self.plan(target, valid["id"]), self.plan(other)):
            with self.assertRaisesRegex(EvidenceError, "DELIVERY_ORDER_MISMATCH"):
                deps.evidence.render(bad)
        self.assertIn("64067", deps.evidence.render(self.plan(target)))
        self.assertNotIn("33513", deps.evidence.render(self.plan(target)))


class DeliveryInvestigationTests(
    SnapshotDeliveryCases, DeliveryScopeCases, unittest.TestCase
):
    def setUp(self):
        self.repo = CanonicalRepository(DATA)
