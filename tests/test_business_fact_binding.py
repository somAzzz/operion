"""Hand-authored regression gold for semantic bindings; no prose classifiers."""

import unittest
from dataclasses import replace

from pydantic import ValidationError

from operion_etl.answer_evidence import AnswerPlan, EvidenceRegistry, TableSelection
from operion_etl.output_guardrails import GuardrailVerdict, verify_answer_plan
from operion_etl.read_tools import AccessScope

C1, C2 = "wwi:organization:customer:1", "wwi:organization:customer:2"


def registry():
    return EvidenceRegistry(
        AccessScope("Demo", frozenset({C1, C2})),
        run_id="run",
        tenant_id="tenant",
        user_id="user",
    )


def add(reg, name, data, args=None):
    return reg.add(name, args or {}, {"ok": True, "data": data})


def orders(*, limit=1, total=30, complete=False):
    return {
        "contract_version": "sales-order-list-v1",
        "data_mode": "snapshot",
        "business_date": "2016-05-31",
        "filters": {"status": "open"},
        "orders": [
            {
                "canonical_id": f"wwi:sales_order:{i}",
                "customer_id": C1 if i % 2 else C2,
                "customer_name": "Alpha" if i % 2 else "Beta",
                "order_number": str(i),
                "net_total_ex_tax": "100.00" if i % 2 else "200.00",
                "currency": "EUR" if i % 2 else "USD",
                "business_status": "Draft" if i % 2 else "Completed",
                "source_status": "open",
            }
            for i in range(1, limit + 1)
        ],
        "completeness": {
            "total_count": total,
            "status": "complete" if complete else "partial",
            "full_source_history": "undetermined",
        },
        "pagination": {"has_more": not complete},
        "customer_order_counts": [{"customer_id": C1, "order_count": 1}],
        "customer_order_counts_scope": "returned_page",
    }


class FactBindingTests(unittest.TestCase):
    def test_total_page_population_and_active_population_are_separate(self):
        reg = registry()
        evidence = add(
            reg,
            "get_customer_portfolio_summary",
            {
                "contract_version": "customer-portfolio-v1",
                "customer_count": 10,
                "customers_with_orders": 8,
                "sales_order_count": 30,
            },
        )
        self.assertEqual(
            [
                ("customer_count", 10),
                ("customers_with_orders", 8),
                ("sales_order_count", 30),
            ],
            [(f["field"], f["value"]) for f in evidence["facts"]],
        )
        text = reg.render(
            AnswerPlan(language="en", facts=[f["id"] for f in evidence["facts"]])
        )
        self.assertIn("Customers (current authorized", text)
        self.assertIn("Customers with sales orders", text)
        self.assertIn("**10**", text)
        self.assertIn("**8**", text)

    def test_production_incident_one_row_does_not_override_total_30(self):
        reg = registry()
        evidence = add(reg, "list_sales_orders", orders())
        facts = {f["field"]: f for f in evidence["facts"]}
        self.assertEqual(30, facts["sales_order_count"]["value"])
        self.assertEqual("filtered_total", facts["sales_order_count"]["coverage"])
        self.assertEqual(1, facts["page_order_count"]["value"])
        self.assertNotIn("customer_count", facts)
        self.assertNotIn("customers_with_orders", facts)
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_answer_plan(
                reg, AnswerPlan(language="en", facts=[facts["sales_order_count"]["id"]])
            ).verdict,
        )

    def test_production_incident_complete_30_rows_and_8_customers(self):
        reg = registry()
        data = orders(limit=30, total=30, complete=True)
        # Eight unique scoped customers; portfolio could also contain two with no orders.
        ids = {f"wwi:organization:customer:{i}" for i in range(1, 11)}
        reg = EvidenceRegistry(AccessScope("Demo", frozenset(ids)))
        for i, row in enumerate(data["orders"]):
            row["customer_id"] = f"wwi:organization:customer:{i % 8 + 1}"
        evidence = add(reg, "list_sales_orders", data)
        facts = {f["field"]: f for f in evidence["facts"]}
        self.assertEqual(8, facts["customers_with_orders"]["value"])
        self.assertNotIn("customer_count", facts)
        for language in ("en", "zh"):
            plan = AnswerPlan(
                language=language,
                facts=[facts["customers_with_orders"]["id"]],
                tables=[TableSelection(table_id=evidence["tables"][0]["id"])],
            )
            self.assertEqual(
                GuardrailVerdict.ALLOW, verify_answer_plan(reg, plan).verdict
            )
            self.assertIn("**8**", reg.render(plan))
            self.assertEqual(30, len(reg.tables[plan.tables[0].table_id].rows))

    def test_values_labels_units_and_scope_cannot_be_overridden(self):
        for field, value in [
            ("value", 999),
            ("currency", "USD"),
            ("label", "All customers"),
            ("scope", "full_history"),
            ("answer", "There are one hundred orders"),
            ("claims", [{"amount": "999"}]),
        ]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                AnswerPlan.model_validate({"facts": [], field: value})
        for field in ("rows", "values", "headers", "entity", "caption"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                TableSelection.model_validate({"table_id": "t", field: ["forged"]})

    def test_order_amount_currency_status_and_identity_stay_on_same_row(self):
        reg = registry()
        evidence = add(
            reg, "list_sales_orders", orders(limit=2, total=2, complete=True)
        )
        table = reg.tables[evidence["tables"][0]["id"]]
        text = reg.render(
            AnswerPlan(
                language="en",
                tables=[
                    TableSelection(
                        table_id=table.id,
                        columns=["net_total_ex_tax", "business_status"],
                    )
                ],
            )
        )
        self.assertIn("wwi:sales\\_order:1", text)
        self.assertIn("EUR | 100.00 | Draft", text)
        self.assertIn("USD | 200.00 | Completed", text)
        self.assertNotIn("EUR | 200.00", text)
        self.assertNotIn("Unit price", text)

    def test_unknown_currency_or_nonfinite_money_cannot_mint_evidence(self):
        for amount, currency in [
            ("100", "eur"),
            ("NaN", "EUR"),
            ("Infinity", "EUR"),
            ("oops", "EUR"),
        ]:
            with self.subTest(amount=amount, currency=currency):
                reg = registry()
                data = orders()
                data["orders"][0].update(net_total_ex_tax=amount, currency=currency)
                evidence = add(reg, "list_sales_orders", data)
                self.assertIn("error", evidence)
                self.assertFalse(reg.facts)
                self.assertFalse(reg.tables)

    def test_unseen_object_or_column_cannot_be_selected(self):
        reg = registry()
        evidence = add(reg, "list_sales_orders", orders())
        for plan, reason in [
            (
                AnswerPlan(language="en", facts=["wwi:sales_order:999"]),
                "FACT_REFERENCE_UNKNOWN",
            ),
            (
                AnswerPlan(
                    language="en",
                    tables=[
                        TableSelection(
                            table_id=evidence["tables"][0]["id"],
                            columns=["delivered_quantity"],
                        )
                    ],
                ),
                "TABLE_COLUMN_UNVERIFIED",
            ),
        ]:
            self.assertEqual(reason, verify_answer_plan(reg, plan).reason_code)

    def test_previous_run_tenant_user_or_scope_evidence_is_rejected(self):
        reg = registry()
        evidence = add(reg, "list_sales_orders", orders())
        ref = evidence["facts"][0]["id"]
        for other in [
            registry(),
            EvidenceRegistry(
                reg.scope, run_id="other", tenant_id="other", user_id="other"
            ),
        ]:
            self.assertEqual(
                "FACT_REFERENCE_UNKNOWN",
                verify_answer_plan(
                    other, AnswerPlan(language="en", facts=[ref])
                ).reason_code,
            )
        fact = reg.facts[ref]
        for ctx in (
            replace(fact.context, run_id="stale"),
            replace(fact.context, scope_id="other-tenant"),
        ):
            reg.facts[ref] = replace(fact, context=ctx)
            self.assertEqual(
                "EVIDENCE_CONTEXT_MISMATCH",
                verify_answer_plan(
                    reg, AnswerPlan(language="en", facts=[ref])
                ).reason_code,
            )

    def test_scope_violations_fail_atomically(self):
        reg = registry()
        data = orders(limit=2, total=2, complete=True)
        data["orders"][1]["customer_id"] = "wwi:organization:customer:999"
        evidence = add(reg, "list_sales_orders", data)
        self.assertEqual("EVIDENCE_SCOPE_MISMATCH", evidence["error"])
        self.assertFalse(reg.facts)
        self.assertFalse(reg.tables)

    def test_conflicting_current_run_records_are_not_arbitrarily_chosen(self):
        reg = registry()
        first = add(reg, "list_sales_orders", orders())
        data = orders()
        data["orders"][0]["net_total_ex_tax"] = "999.00"
        second = add(reg, "list_sales_orders", data)
        for evidence in (first, second):
            plan = AnswerPlan(
                language="en",
                tables=[TableSelection(table_id=evidence["tables"][0]["id"])],
            )
            self.assertEqual(
                "EVIDENCE_CONFLICT", verify_answer_plan(reg, plan).reason_code
            )

    def test_equivalent_decimal_formats_do_not_create_false_conflicts(self):
        reg = registry()
        first = add(reg, "list_sales_orders", orders())
        data = orders()
        data["orders"][0]["net_total_ex_tax"] = "100.0"
        second = add(reg, "list_sales_orders", data)
        for evidence in (first, second):
            plan = AnswerPlan(
                language="en",
                tables=[TableSelection(table_id=evidence["tables"][0]["id"])],
            )
            self.assertEqual(
                GuardrailVerdict.ALLOW, verify_answer_plan(reg, plan).verdict
            )

    def test_filters_are_rendered_and_cannot_be_relabelled_as_portfolio(self):
        reg = registry()
        evidence = add(
            reg,
            "list_sales_orders",
            orders(),
            {
                "customer": C1,
                "status": "open",
                "date_from": "2016-01-01",
                "cursor": "page2",
            },
        )
        ref = next(
            f["id"] for f in evidence["facts"] if f["field"] == "sales_order_count"
        )
        text = reg.render(AnswerPlan(language="en", facts=[ref]))
        self.assertIn("filtered", text)
        self.assertIn("2016-01-01", text)
        self.assertIn("Following page", text)
        self.assertIn("full source history", text)

    def test_supplier_count_uses_purchase_semantics(self):
        reg = EvidenceRegistry(
            AccessScope("Demo", frozenset(), frozenset({"supplier-a"}))
        )
        evidence = add(
            reg,
            "get_supplier_overview",
            {
                "contract_version": "supplier-overview-v2",
                "supplier": {"canonical_id": "supplier-a", "name": "Supplier"},
                "orders": [],
                "order_count": 0,
            },
        )
        self.assertEqual(
            {("purchase_order_count", 0), ("page_order_count", 0)},
            {(f["field"], f["value"]) for f in evidence["facts"]},
        )


if __name__ == "__main__":
    unittest.main()
