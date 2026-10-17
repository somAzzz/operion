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
    def test_paged_order_total_is_separate_from_page_customer_counts(self):
        calls = [
            {
                "name": "list_sales_orders",
                "result": {
                    "ok": True,
                    "data": {
                        "orders": [{"canonical_id": "wwi:sales_order:1"}],
                        "completeness": {
                            "status": "partial",
                            "returned_count": 1,
                            "total_count": 30,
                        },
                        "customer_order_counts": [
                            {
                                "customer_id": "wwi:organization:customer:65",
                                "customer_name": "Tailspin Toys",
                                "order_count": 1,
                            }
                        ],
                        "customer_order_counts_scope": "returned_page",
                    },
                },
            }
        ]
        for answer, allowed in [
            ("We have 30 sales orders in the current authorized scope.", True),
            ("We have 1 sales order in total.", False),
            ("This page contains 1 sales order.", True),
            ("This page contains 30 sales orders.", False),
            ("Tailspin Toys has 1 sales order.", False),
            ("Tailspin Toys has 30 sales orders.", False),
            ("On this page, Tailspin Toys has 1 sales order.", True),
        ]:
            with self.subTest(answer=answer):
                self.assertEqual(
                    allowed,
                    verify_business_answer(calls, answer).verdict
                    == GuardrailVerdict.ALLOW,
                )

    def test_portfolio_total_and_customer_totals_do_not_compete(self):
        calls = [
            {
                "name": "get_customer_order_distribution",
                "result": {
                    "ok": True,
                    "data": {
                        "sales_order_count": 30,
                        "customers": [{"customer_name": "Alpha", "order_count": 10}],
                    },
                },
            }
        ]
        for answer, allowed in [
            ("We have 30 sales orders.", True),
            ("We have 10 sales orders.", False),
            ("Alpha has 10 sales orders.", True),
            ("Alpha has 30 sales orders.", False),
        ]:
            with self.subTest(answer=answer):
                self.assertEqual(
                    allowed,
                    verify_business_answer(calls, answer).verdict
                    == GuardrailVerdict.ALLOW,
                )

    def test_customer_count_requires_current_tool_evidence(self):
        calls = [
            {
                "name": "get_customer_portfolio_summary",
                "result": {
                    "ok": True,
                    "data": {"customer_count": 10},
                },
            }
        ]
        for answer in ["You have **1 customer**.", "客户数量：1", "共有一位客户"]:
            with self.subTest(answer=answer):
                self.assertEqual(
                    "CUSTOMER_COUNT_MISMATCH",
                    verify_business_answer(calls, answer).reason_code,
                )
                self.assertEqual(
                    "CUSTOMER_COUNT_UNVERIFIED",
                    verify_business_answer([], answer).reason_code,
                )
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(
                calls, "You have **10 customers** in the current authorized scope."
            ).verdict,
        )
        search = [
            {
                "name": "search_customers",
                "result": {
                    "ok": True,
                    "data": {
                        "query": "",
                        "results": [{}, {}],
                        "completeness": {"status": "partial"},
                    },
                },
            }
        ]
        self.assertNotEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(search, "2 customers").verdict,
        )
        search[0]["result"]["data"]["completeness"]["status"] = "complete"
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(search, "2 customers").verdict,
        )

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
