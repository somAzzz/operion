import asyncio
import os
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_delivery_investigation import (
    DATA,
    SCOPE,
    DeliveryScopeCases,
    DeliveryTestHelpers,
)

from operion_etl.agent_runtime import (
    AgentSettings,
    create_operion_agent,
    repository_from_environment,
)
from operion_etl.answer_evidence import AnswerPlan, EvidenceError
from operion_etl.mcp_server import create_server
from operion_etl.read_tools import (
    AccessScope,
    CanonicalRepository,
    NotFoundError,
    ScopeDeniedError,
)
from operion_etl.wwi_delivery import DeliveryOrder, WwiDeliveryReader


class DirectDeliveryTests(DeliveryTestHelpers, unittest.TestCase):
    def setUp(self):
        self.reader = Mock(spec=WwiDeliveryReader)
        self.repo = CanonicalRepository(DATA, delivery_reader=self.reader)

    def test_detail_requires_invoice_to_belong_to_the_requested_order(self):
        self.reader.read.return_value = DeliveryOrder(
            order_id=66823,
            customer_id=65,
            order_date="2016-02-17",
            expected_date="2016-02-18",
            queried_at="2026-11-08T12:00:00Z",
            invoices=[
                dict(
                    invoice_id=64067,
                    invoice_order_id=66823,
                    invoice_customer_id=65,
                    credit_note=False,
                    confirmed_at="2016-02-19T07:25:00",
                    has_recipient=True,
                )
            ],
            issues=[],
            lines=[],
        )
        self.assertEqual(
            64067,
            self.repo.get_delivery_record("66823", "invoice", "64067", SCOPE)[
                "invoice"
            ]["invoice_id"],
        )
        with self.assertRaises(NotFoundError):
            self.repo.get_delivery_record("66823", "invoice", "33513", SCOPE)
        self.reader.read.assert_called_with(66823, [65, 935], [])

    def test_wwi_runtime_defaults_to_sql_and_snapshot_is_explicit(self):
        env = {
            "OPERION_CANONICAL_DIR": str(DATA),
            "OPERION_IDENTITY_MAP": "reports/demo-wwi-v1/identity_map.csv",
            "OPERION_OBSERVED_AT": "2026-11-08T00:00:00Z",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertIsInstance(
                repository_from_environment().delivery_reader, WwiDeliveryReader
            )
            os.environ["OPERION_DELIVERY_SOURCE"] = "snapshot"
            self.assertIsNone(repository_from_environment().delivery_reader)
            os.environ["OPERION_DELIVERY_SOURCE"] = "typo"
            with self.assertRaises(RuntimeError):
                repository_from_environment()

    def test_direct_card_uses_only_source_observations(self):
        self.reader.read.return_value = DeliveryOrder(
            customer_id=65,
            order_id=66823,
            order_date="2016-02-17",
            expected_date="2016-02-21",
            queried_at="2026-11-08T12:00:00Z",
            invoices=[],
            issues=[],
            lines=[
                dict(
                    canonical_id="wwi:sales_order_line:210128",
                    stock_item_id=193,
                    ordered_quantity=7,
                    picked_quantity=0,
                    uom="Each",
                )
            ],
        )
        deps = self.deps("Investigate order 66823.")
        result = self.query(deps, "66823")
        answer = deps.evidence.render(self.plan(result))
        self.reader.read.assert_called_once_with(66823, [65, 935], [])
        for phrase in (
            "WWI SQL Server query time",
            "2026-11-08T12:00:00+00:00",
            "2016-02-21",
            "picked 0 Each",
            "No linked invoice returned by WWI SQL Server",
        ):
            self.assertIn(phrase, answer)
        self.assertNotIn("64067", answer)
        self.assertNotIn("snapshot_id", result["data"])

    def test_unavailable_and_missing_source_order_never_use_snapshot(self):
        for missing in (False, True):
            self.reader.read.side_effect = None if missing else OSError("unavailable")
            self.reader.read.return_value = None
            deps = self.deps("Investigate order 66823.")
            result = self.query(deps, "66823")
            self.assertEqual(
                "not_found" if missing else "source_unavailable",
                result["error"]["code"],
            )
            self.assertFalse(result["answer_evidence"]["tables"])
            self.assertNotIn("64067", deps.evidence.render(AnswerPlan(language="en")))

    def test_unauthorized_order_never_reaches_sql(self):
        with self.assertRaises(ScopeDeniedError):
            self.repo.get_order_delivery_evidence(
                "66823", AccessScope("AI Demo GmbH", frozenset())
            )
        self.reader.read.assert_not_called()

    def test_T05_publishes_lookup_failure_without_another_model_decision(self):
        self.reader.read.side_effect = OSError("private connection details")
        question = "Investigate delivery for order 66823."
        deps = self.deps(question)
        deps.allowed_tools = frozenset({"get_order_delivery_evidence"})
        requests = []

        def respond(messages, info):
            requests.append(info)
            call = (
                ToolCallPart("get_order_delivery_evidence", {"order_id": "66823"})
                if len(requests) == 1
                else ToolCallPart(
                    "present_answer",
                    {"plan": {"language": "en", "notice": "unsupported"}},
                )
            )
            return ModelResponse(parts=[call])

        agent = create_operion_agent(AgentSettings(), model=FunctionModel(respond))
        result = agent.run_sync(question, deps=deps)
        self.assertEqual(1, len(requests))
        self.assertIn(
            "could not query WWI SQL Server for delivery evidence", result.output
        )
        self.assertIn(
            "Whether a linked invoice or delivery confirmation exists is unknown",
            result.output,
        )
        for text in ("No linked invoice", "64067", "private connection details"):
            self.assertNotIn(text, result.output)

    def test_T05_cannot_finish_with_another_orders_failed_query(self):
        self.reader.read.side_effect = OSError("unavailable")
        deps = self.deps("Investigate order 66823.")
        self.query(deps, "31349")
        self.query(deps, "66823")
        self.assertFalse(deps.evidence.only_wwi_delivery_query_failed())
        with self.assertRaisesRegex(EvidenceError, "DELIVERY_ORDER_MISMATCH"):
            deps.evidence.render(AnswerPlan(language="en"))

    def test_complaint_lookup_failure_is_not_a_failed_sql_query(self):
        from types import SimpleNamespace

        from operion_etl import complaint
        from operion_etl.agent_runtime import get_complaint_context

        deps = self.deps(f"Read Twenty Note {complaint.NOTE_ID}.")
        result = get_complaint_context(SimpleNamespace(deps=deps), complaint.NOTE_ID)
        self.reader.read.assert_not_called()
        self.assertEqual("source_unavailable", result["error"]["code"])
        self.assertFalse(deps.evidence.only_wwi_delivery_query_failed())
        self.assertNotIn(
            "WWI SQL Server", deps.evidence.render(AnswerPlan(language="en"))
        )


@unittest.skipUnless(
    os.environ.get("OPERION_TEST_WWI_SQLSERVER") == "1",
    "requires the restored WWI SQL Server",
)
class SqlServerAcceptanceTests(DeliveryScopeCases, unittest.TestCase):
    def setUp(self):
        self.reader = WwiDeliveryReader.from_environment()
        self.repo = CanonicalRepository(DATA, delivery_reader=self.reader)

    def test_T01_confirmation_and_T02_complete_empty(self):
        for order, lookup in (
            ("66823", "linked_invoices"),
            ("73279", "no_linked_invoice"),
        ):
            result = self.repo.get_order_delivery_evidence(order, SCOPE)
            self.assertEqual("live", result["data_mode"])
            self.assertEqual(lookup, result["lookup"])
            if order == "66823":
                self.assertEqual(
                    "2016-02-19T07:25:00", result["invoices"][0]["confirmed_at"]
                )
                self.assertEqual(
                    1, result["invoices"][0]["calendar_days_from_expected"]
                )
                self.assertGreater(
                    result["queried_at"], result["invoices"][0]["confirmed_at"]
                )
        self.assertIsNone(self.reader.read(66823, [935], []))

    def test_mcp_reads_the_same_scoped_sql_evidence(self):
        response = asyncio.run(
            create_server(self.repo, SCOPE).call_tool(
                "get_order_delivery_evidence", {"order_id": "66823"}
            )
        )
        data = response.structured_content
        self.assertEqual("live", data["data_mode"])
        self.assertEqual("wwi:sales_order:66823", data["order_id"])
        self.assertEqual(64067, data["invoices"][0]["invoice_id"])
        self.assertTrue(data["queried_at"])

    def test_T05_unreachable_sql_with_intact_snapshot(self):
        self.repo = CanonicalRepository(
            DATA, delivery_reader=replace(self.reader, host="127.0.0.1", port=1)
        )
        deps = self.deps("Investigate order 66823.")
        result = self.query(deps, "66823")
        self.assertEqual("source_unavailable", result["error"]["code"])
        self.assertFalse(result["answer_evidence"]["tables"])
