"""Independent, hand-authored gold: no production helper builds expectations."""

import unittest

from operion_etl.e2_evaluation import grade_case
from operion_etl.output_guardrails import GuardrailVerdict, verify_business_answer


def order(identity, amount, currency, status):
    return {
        "name": "get_sales_order",
        "result": {
            "ok": True,
            "data": {
                "order": {
                    "canonical_id": identity,
                    "net_total_ex_tax": amount,
                    "currency": currency,
                    "business_status": status,
                    "source_status": "open",
                    "unit_price_ex_tax": "5.00",
                }
            },
        },
    }


class FactBindingTests(unittest.TestCase):
    def test_currency_is_part_of_the_fact_and_scorer_rejects_it(self):
        calls = [order("wwi:sales_order:1", "177.60", "USD", "Draft")]
        for answer, allowed in [
            ("wwi:sales_order:1 金额 EUR 177.60，状态 Draft", False),
            ("wwi:sales_order:1 金额 USD 177.60，状态 Draft", True),
            ("wwi:sales_order:1 金额 177.60 美元，状态 Draft", True),
            ("wwi:sales_order:1 金额 177.60 欧元，状态 Draft", False),
            ("wwi:sales_order:1 金额 USD 5.00", False),
            ("wwi:sales_order:1 状态 open", False),
            ("wwi:sales_order:1 来源状态 open", True),
        ]:
            with self.subTest(answer=answer):
                self.assertEqual(
                    allowed,
                    verify_business_answer(calls, answer).verdict
                    == GuardrailVerdict.ALLOW,
                )
                if not allowed:
                    self.assertTrue(
                        grade_case({"tool": "get_sales_order"}, calls, answer)
                    )

    def test_total_cannot_borrow_unit_price_in_the_same_clause(self):
        calls = [order("wwi:sales_order:1", "100", "EUR", "Draft")]
        self.assertNotEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(
                calls, "wwi:sales_order:1 单价 EUR 5，总额 EUR 5"
            ).verdict,
        )
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(
                calls, "wwi:sales_order:1 单价 EUR 5，总额 EUR 100"
            ).verdict,
        )

    def test_multiple_orders_cannot_exchange_facts(self):
        calls = [
            order("wwi:sales_order:1", "100", "EUR", "Draft"),
            order("wwi:sales_order:2", "200", "EUR", "Completed"),
        ]
        for answer, allowed in [
            (
                "wwi:sales_order:1 金额 EUR 200，状态 Completed；wwi:sales_order:2 金额 EUR 100，状态 Draft",
                False,
            ),
            (
                "wwi:sales_order:1 金额 EUR 100，状态 Draft；wwi:sales_order:2 金额 EUR 200，状态 Completed",
                True,
            ),
            ("金额 EUR 100", False),
            ("wwi:sales_order:1 和 wwi:sales_order:2 金额 EUR 100", False),
        ]:
            with self.subTest(answer=answer):
                self.assertEqual(
                    allowed,
                    verify_business_answer(calls, answer).verdict
                    == GuardrailVerdict.ALLOW,
                )

    def test_evaluator_accepts_correct_multi_object_answer(self):
        calls = [
            order("wwi:sales_order:1", "100", "EUR", "Draft"),
            order("wwi:sales_order:2", "200", "EUR", "Completed"),
        ]
        self.assertEqual(
            [],
            grade_case(
                {"tool": "get_sales_order"},
                calls,
                "wwi:sales_order:1 金额 EUR 100，状态 Draft；wwi:sales_order:2 金额 EUR 200，状态 Completed",
            ),
        )

    def test_customer_overview_counts_are_bound(self):
        calls = [
            {
                "name": "get_customer_overview",
                "result": {
                    "ok": True,
                    "data": {
                        "customer": {
                            "canonical_id": f"wwi:organization:customer:{i}",
                            "name": name,
                        },
                        "orders": [{}] * count,
                    },
                },
            }
            for i, name, count in [(1, "Alpha", 0), (2, "Beta", 3)]
        ]
        for answer, allowed in [
            (
                "wwi:organization:customer:1 has 3 orders; wwi:organization:customer:2 has 0 orders",
                False,
            ),
            (
                "wwi:organization:customer:1 has 0 orders; wwi:organization:customer:2 has 3 orders",
                True,
            ),
            ("Alpha has 0 orders; Beta has 3 orders", True),
            ("Alpha has 3 orders; Beta has 0 orders", False),
            ("There are 3 orders", False),
        ]:
            with self.subTest(answer=answer):
                self.assertEqual(
                    allowed,
                    verify_business_answer(calls, answer).verdict
                    == GuardrailVerdict.ALLOW,
                )

    def test_capability_call_cannot_disable_object_checks(self):
        calls = [
            {"name": "check_operation_capability", "result": {"ok": True, "data": {}}}
        ]
        self.assertNotEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(calls, "wwi:sales_order:999").verdict,
        )

    def test_unknown_currency_and_conflicting_evidence_are_not_accepted(self):
        calls = [order("wwi:sales_order:1", "100", "", "Draft")]
        self.assertNotEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(calls, "金额 EUR 100").verdict,
        )
        calls.append(order("wwi:sales_order:1", "200", "EUR", "Draft"))
        self.assertNotEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(calls, "金额 EUR 200").verdict,
        )
