import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pydantic_ai import ModelRetry
from test_delivery_investigation import DATA, DeliveryTestHelpers

from operion_etl import complaint
from operion_etl.agent_runtime import (
    AgentDependencies,
    get_complaint_context,
    get_purchase_order,
)
from operion_etl.answer_evidence import AnswerPlan, EvidenceError, EvidenceRegistry
from operion_etl.identity_readback import TwentyReadClient
from operion_etl.read_tools import (
    AccessScope,
    CanonicalRepository,
    NotFoundError,
    ScopeDeniedError,
)
from operion_etl.twenty import read_env
from operion_etl.wwi_delivery import WwiDeliveryReader

COMPANY = "00a9c9c4-3a6a-55ef-81ab-270f84177d19"
SCOPE = AccessScope(
    "AI Demo GmbH",
    frozenset({complaint.CUSTOMER, "wwi:organization:customer:58"}),
    frozenset({"wwi:organization:supplier:7"}),
)


class ComplaintTests(unittest.TestCase):
    def test_signed_card_survives_subsequent_purchase_lookup_attempt(self):
        repo = CanonicalRepository(DATA)
        deps = AgentDependencies(
            repo,
            SCOPE,
            "operator",
            user_request="Investigate order 66823 using invoice 33513 and purchase order 1904.",
        )
        result = DeliveryTestHelpers.query(self, deps, "66823")
        with self.assertRaises(ModelRetry):
            get_purchase_order(SimpleNamespace(deps=deps), "1904")
        text = deps.evidence.render(DeliveryTestHelpers.plan(self, result))
        self.assertIn("Invoice 33513 is absent", text)
        self.assertIn("64067", text)

    def test_followup_cannot_replace_complaint_order_with_same_customer_order(self):
        reader = Mock()
        deps = AgentDependencies(
            CanonicalRepository(DATA, delivery_reader=reader),
            SCOPE,
            "operator",
            user_request="Use order 31349 and invoice 33513 to prove receipt.",
            prior_note={"customer_id": complaint.CUSTOMER, "order_id": "66823"},
        )
        for order in ("31349", "66823"):
            with self.assertRaises(ModelRetry):
                DeliveryTestHelpers.query(self, deps, order)
        reader.read.assert_not_called()

    def test_purchase_order_is_not_the_sales_subject(self):
        for request, target in (
            (
                "For order 66823, did these units come from purchase order 1904?",
                "wwi:sales_order:66823",
            ),
            ("Can purchase order 1904 prove the origin?", None),
            ("Look up 89; use the invoice for order 31349.", None),
        ):
            with self.subTest(request=request):
                self.assertEqual(
                    target,
                    EvidenceRegistry(SCOPE, user_request=request).delivery_target,
                )

    def test_existing_erp_customer_can_have_no_twenty_company(self):
        client = Mock()
        client.http.get_json.return_value = {"totalCount": 0, "data": {"companies": []}}
        context = complaint.customer_context(client, "wwi:organization:customer:58")
        self.assertEqual("no_crm_mapping", context["status"])
        client.http.get_json.assert_called_once_with(
            "/rest/companies",
            {"filter": "wwiExternalId[eq]:wwi:organization:customer:58", "limit": 2},
        )

    def test_wrong_company_or_borrowed_person_cannot_be_used(self):
        c = Mock()
        person_id = "0e7b80f1-056a-5fab-9d58-bf8671141233"
        targets = [
            {"noteId": complaint.NOTE_ID, "targetCompanyId": COMPANY},
            {"noteId": complaint.NOTE_ID, "targetPersonId": person_id},
        ]
        company = {
            "id": COMPANY,
            "wwiExternalId": complaint.CUSTOMER,
            "name": "Tailspin",
        }
        for sender_company, email in (
            (COMPANY, "other@example.com"),
            ("other", "sender@example.com"),
        ):
            c.http.get_json.side_effect = [
                {"data": {"noteTargets": targets}, "totalCount": 2},
                {"data": {"company": company}},
                {"data": {"companies": [company]}, "totalCount": 1},
                {"data": {"people": []}, "totalCount": 0},
                {
                    "data": {
                        "note": {
                            "id": complaint.NOTE_ID,
                            "title": complaint.TITLE,
                            "bodyV2": {
                                "markdown": "From: sender@example.com\n\nNo delivery"
                            },
                        }
                    }
                },
                {
                    "data": {
                        "person": {
                            "id": person_id,
                            "companyId": sender_company,
                            "emails": {"primaryEmail": email},
                        }
                    }
                },
            ]
            result = complaint.read_complaint(c, complaint.NOTE_ID, SCOPE.customer_ids)
            self.assertEqual({"status": "unconfirmed"}, result["sender"])
        c.http.get_json.side_effect = [
            {"data": {"noteTargets": targets}, "totalCount": 2},
            {
                "data": {
                    "company": dict(
                        company, wwiExternalId="wwi:organization:customer:11"
                    )
                }
            },
        ]
        with self.assertRaises(complaint.ComplaintOutsideScope):
            complaint.read_complaint(c, complaint.NOTE_ID, SCOPE.customer_ids)

    def test_unauthorized_complaint_does_not_read_twenty(self):
        client = Mock()
        repo = CanonicalRepository(
            DATA, delivery_reader=Mock(), complaint_client=client
        )
        with self.assertRaises(ScopeDeniedError):
            repo.get_delivery_complaint(AccessScope("AI Demo GmbH", frozenset()))
        client.http.get_json.assert_not_called()


@unittest.skipUnless(
    os.environ.get("OPERION_TEST_DELIVERY_COMPLAINT") == "1",
    "requires seeded Twenty and WWI",
)
class LiveComplaintTests(DeliveryTestHelpers, unittest.TestCase):
    def setUp(self):
        env = read_env()
        crm = TwentyReadClient(
            env.get("TWENTY_API_BASE_URL", "http://127.0.0.1:3000"),
            env["TWENTY_API_KEY_READ_ONLY"],
        )
        self.repo = CanonicalRepository(
            DATA,
            delivery_reader=WwiDeliveryReader.from_environment(),
            complaint_client=crm,
        )

    def test_mapped_erp_order_outside_snapshot_remains_scoped(self):
        self.assertNotIn("89", {r["source_id"] for r in self.repo.data["sales_orders"]})
        result = self.repo.get_order_delivery_evidence("89", SCOPE)
        self.assertEqual("wwi:organization:customer:58", result["customer_id"])
        self.assertEqual("mapped", result["crm"]["status"])
        with self.assertRaisesRegex(NotFoundError, "no matching order"):
            self.repo.get_order_delivery_evidence(
                "89", AccessScope("AI Demo GmbH", frozenset({complaint.CUSTOMER}))
            )

    def test_live_order_without_a_crm_mapping_keeps_its_erp_evidence(self):
        client = Mock()
        client.http.get_json.return_value = {"totalCount": 0, "data": {"companies": []}}
        repo = CanonicalRepository(
            DATA, delivery_reader=self.repo.delivery_reader, complaint_client=client
        )
        result = repo.get_order_delivery_evidence("66823", SCOPE)
        self.assertEqual("no_crm_mapping", result["crm"]["status"])
        self.assertEqual(
            [64067], [invoice["invoice_id"] for invoice in result["invoices"]]
        )
        self.assertNotIn("company_id", result["crm"])

    def test_note_to_draft_and_forced_invalid_purchase_allocation(self):
        deps = AgentDependencies(
            self.repo,
            SCOPE,
            "operator",
            user_request=f"Read Twenty Note {complaint.NOTE_ID}.",
        )
        crm = get_complaint_context(SimpleNamespace(deps=deps), complaint.NOTE_ID)
        self.assertEqual(
            ["get_complaint_context"], [call["name"] for call in deps.tool_calls]
        )
        self.assertIn("Hanuman Dubey", deps.evidence.render(self.plan(crm)))
        prior = deps.evidence.selection_manifest(self.plan(crm))["complaint_context"]
        deps = AgentDependencies(
            self.repo,
            SCOPE,
            "operator",
            user_request="Now investigate the delivery.",
            prior_note=prior,
        )
        result = self.query(deps, "66823")
        data = result["data"]
        self.assertEqual(complaint.NOTE_ID, data["complaint"]["note_id"])
        self.assertTrue(data["crm"]["has_linked_person"])
        (issue,) = data["issues"]
        self.assertEqual(
            (305669, 64067, 193),
            (issue["issue_id"], issue["invoice_id"], issue["stock_item_id"]),
        )
        self.assertEqual(
            [(305626, 1904), (305233, 1902)],
            [
                (r["receipt_id"], r["purchase_order_id"])
                for r in issue["prior_receipts"]
            ],
        )
        bad = deps.evidence.add(
            "get_order_delivery_evidence",
            {"order_id": "66823"},
            {
                "ok": True,
                "data": dict(
                    data,
                    stock_allocation={"purchase_order_id": 1904, "issue_id": 305669},
                ),
            },
        )
        self.assertEqual("UNVERIFIED_STOCK_ALLOCATION", bad["error"])
        self.assertFalse(bad["tables"])
        with self.assertRaises(EvidenceError):
            deps.evidence.render(self.plan(result, "PO:1904:supplied:305669"))
        text = deps.evidence.render(self.plan(result))
        self.assertIn("Purchase source unverified", text)
        self.assertIn(
            f"CRM sender: [Hanuman Dubey](/orders/66823?open=sender&record=0e7b80f1-056a-5fab-9d58-bf8671141233&note={complaint.NOTE_ID})",
            text,
        )
        for kind, record_id in (
            ("note", complaint.NOTE_ID),
            ("company", f"{COMPANY}&note={complaint.NOTE_ID}"),
            ("person", data["crm"]["order_contact"]["id"]),
        ):
            self.assertIn(f"/orders/66823?open={kind}&record={record_id}", text)
        self.assertIn("Order contact: Hanuman Dubey", text)
        draft = text.split("Customer reply draft")[1]
        self.assertIn("pending human review", draft)
        self.assertNotIn("1904", draft)
        self.assertNotIn("Litware", draft)
        self.assertNotIn("33513", text)

    def test_complaint_guards_wrong_subject_and_unverified_answer(self):
        deps = AgentDependencies(
            self.repo,
            SCOPE,
            "operator",
            user_request=f"Read Twenty Note {complaint.NOTE_ID}.",
        )
        with self.assertRaises(EvidenceError):
            deps.evidence.render(AnswerPlan(language="en", notice="unsupported"))
        with self.assertRaises(ModelRetry):
            self.query(deps, "66823")
        get_complaint_context(SimpleNamespace(deps=deps), complaint.NOTE_ID)
        wrong = self.query(deps, "31349")
        self.assertFalse(wrong["ok"])
        self.assertFalse(wrong["answer_evidence"]["facts"])

    def test_failed_wwi_followup_retains_only_the_scoped_crm_observation(self):
        import asyncio

        from operion_etl.mcp_server import create_server

        response = asyncio.run(
            create_server(self.repo, SCOPE).call_tool(
                "get_complaint_context", {"note_id": complaint.NOTE_ID}
            )
        )
        note = response.structured_content
        self.assertEqual("verified", note["sender"]["status"])
        self.repo.delivery_reader = Mock()
        self.repo.delivery_reader.read.side_effect = OSError()
        deps = AgentDependencies(
            self.repo,
            SCOPE,
            "operator",
            user_request="Now check the delivery.",
            prior_note=note,
        )
        with self.assertRaises(ModelRetry):
            get_purchase_order(SimpleNamespace(deps=deps), "1904")
        self.query(deps, "66823")
        text = deps.evidence.render(AnswerPlan(language="en"))
        for expected in (
            note["claim"],
            note["source_observed_at"],
            f"CRM sender: [Hanuman Dubey](/orders/66823?open=sender&record=0e7b80f1-056a-5fab-9d58-bf8671141233&note={complaint.NOTE_ID})",
            "could not query WWI",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("64067", text)
        other = EvidenceRegistry(
            AccessScope("AI Demo GmbH", frozenset()), prior_note=note
        )
        self.assertIsNone(other.note)

    def test_supplier_scope_filters_receipts_before_publication(self):
        result = self.repo.get_order_delivery_evidence(
            "66823", AccessScope("AI Demo GmbH", SCOPE.customer_ids)
        )
        self.assertEqual([], result["issues"][0]["prior_receipts"])
