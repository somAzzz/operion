"""Contract adapters exercised against actual repository payloads, not mock shapes."""

import unittest
from pathlib import Path

from operion_etl.answer_evidence import AnswerPlan, EvidenceRegistry, TableSelection
from operion_etl.read_tools import AccessScope, CanonicalRepository


class EvidenceContractTests(unittest.TestCase):
    def test_every_read_contract_can_render_its_repository_output(self):
        repo = CanonicalRepository(Path("tests/fixtures/wwi-small"))
        customer_ids = frozenset(
            row["canonical_id"]
            for row in repo.data["organizations"]
            if row["roles"] == "customer"
        )
        supplier_ids = frozenset(
            row["canonical_id"]
            for row in repo.data["organizations"]
            if row["roles"] == "supplier"
        )
        scope = AccessScope("AI Demo GmbH", customer_ids, supplier_ids)
        customer = repo.data["sales_orders"][0]["customer_canonical_id"]
        order = repo.data["sales_orders"][0]["canonical_id"]
        customer_name = next(
            row["name"]
            for row in repo.data["organizations"]
            if row["canonical_id"] == customer
        )
        calls = {
            "get_customer_portfolio_summary": lambda: repo.customer_portfolio_summary(
                scope
            ),
            "get_customer_order_distribution": lambda: repo.customer_order_distribution(
                scope
            ),
            "get_customer_overview": lambda: repo.customer_overview(customer, scope),
            "get_organization_orders": lambda: repo.get_organization_orders(
                customer, scope
            ),
            "get_customer_order_context": lambda: repo.get_customer_order_context(
                customer_name, order, scope
            ),
            "search_customers": lambda: repo.search_customers("", scope),
            "search_suppliers": lambda: repo.search_suppliers("", scope),
            "search_contacts": lambda: repo.search_contacts("a", scope),
            "list_sales_orders": lambda: repo.list_sales_orders(scope),
            "list_purchase_orders": lambda: repo.list_purchase_orders(scope),
            "get_sales_order": lambda: repo.get_sales_order(order, scope),
            "check_fulfillment": lambda: repo.fulfillment_case(
                repo.data["fulfillment_scenarios"][0]["case_id"]
            ),
        }
        if supplier_ids:
            calls["get_supplier_overview"] = lambda: repo.supplier_overview(
                next(iter(supplier_ids)), scope
            )
        if repo.data["purchase_orders"]:
            calls["get_purchase_order"] = lambda: repo.get_purchase_order(
                repo.data["purchase_orders"][0]["canonical_id"], scope
            )
        if repo.data["contacts"]:
            calls["get_contact_by_name"] = lambda: repo.get_contact_by_name(
                next(
                    row["full_name"]
                    for row in repo.data["contacts"]
                    if row["company_canonical_id"] in customer_ids | supplier_ids
                ),
                scope,
            )
        for tool, call in calls.items():
            with self.subTest(tool=tool):
                reg = EvidenceRegistry(scope)
                data = call()
                evidence = reg.add(tool, {}, {"ok": True, "data": data})
                self.assertNotIn("error", evidence)
                plan = AnswerPlan(
                    language="en",
                    facts=[f["id"] for f in evidence["facts"]],
                    tables=[
                        TableSelection(table_id=t["id"]) for t in evidence["tables"]
                    ],
                )
                self.assertTrue(reg.render(plan))


if __name__ == "__main__":
    unittest.main()
