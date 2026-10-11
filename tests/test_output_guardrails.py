import unittest

from operion_etl.output_guardrails import GuardrailVerdict, verify_business_answer


class OutputGuardrailTests(unittest.TestCase):
    def test_paged_filtered_total_is_usable_without_full_history_claim(self):
        calls = [
            {
                "name": "list_sales_orders",
                "result": {
                    "ok": True,
                    "data": {
                        "orders": [{"canonical_id": "wwi:order:1"}],
                        "completeness": {
                            "status": "partial",
                            "total_count": 7,
                            "full_source_history": "undetermined",
                        },
                    },
                },
            }
        ]
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(calls, "当前筛选条件下有 7 张订单。").verdict,
        )
        self.assertEqual(
            "ORDER_COUNT_MISMATCH",
            verify_business_answer(calls, "当前筛选条件下有 1 张订单。").reason_code,
        )
        self.assertEqual(
            "ORDER_COUNT_MISMATCH",
            verify_business_answer(
                calls, "The customer has **100** sales orders."
            ).reason_code,
        )
        self.assertEqual(
            "HISTORY_SCOPE_UNVERIFIED",
            verify_business_answer(calls, "全部历史订单共有 7 张订单。").reason_code,
        )

    def test_business_claims_require_server_evidence(self):
        calls = [
            {
                "name": "get_sales_order",
                "result": {
                    "ok": True,
                    "data": {
                        "order": {
                            "canonical_id": "wwi:order:1",
                            "business_status": "To Deliver",
                            "net_total_ex_tax": "321.00",
                        }
                    },
                },
            }
        ]
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(
                calls, "wwi:order:1 状态为待交付，金额 EUR 321.00。"
            ).verdict,
        )
        for answer, code in (
            ("金额 EUR 999.00。", "AMOUNT_UNVERIFIED"),
            ("Net amount excluding tax: 999.00", "AMOUNT_UNVERIFIED"),
            ("wwi:order:2 状态为待交付。", "OBJECT_ID_UNVERIFIED"),
            ("状态为已取消。", "STATUS_UNVERIFIED"),
            ("Current status: **Draft**", "STATUS_UNVERIFIED"),
            ("库存充足，可以履约。", "FULFILLMENT_UNVERIFIED"),
        ):
            with self.subTest(answer=answer):
                self.assertEqual(
                    code, verify_business_answer(calls, answer).reason_code
                )

    def test_customer_count_cannot_validate_an_unnamed_portfolio_total(self):
        calls = [
            {
                "name": "get_customer_order_distribution",
                "result": {
                    "ok": True,
                    "data": {
                        "sales_order_count": 10,
                        "customers": [
                            {"customer_name": "Tailspin Toys", "order_count": 4}
                        ],
                    },
                },
            }
        ]
        self.assertEqual(
            "ORDER_COUNT_MISMATCH",
            verify_business_answer(calls, "The portfolio has 4 orders.").reason_code,
        )
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(calls, "Tailspin Toys has 4 orders.").verdict,
        )
        self.assertEqual(
            "ORDER_COUNT_MISMATCH",
            verify_business_answer(calls, "Tailspin Toys has 10 orders.").reason_code,
        )

    def test_source_failure_cannot_be_reported_as_zero_orders(self):
        calls = [
            {
                "name": "list_sales_orders",
                "result": {"ok": False, "error": {"code": "source_unavailable"}},
            }
        ]
        self.assertEqual(
            "ORDER_COUNT_UNVERIFIED",
            verify_business_answer(calls, "客户没有订单。").reason_code,
        )
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer(calls, "订单来源不可用，目前无法确认。").verdict,
        )

    def test_refusal_does_not_become_zero_order_claim(self):
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer([], "No orders were deleted.").verdict,
        )
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer([], "没有订单被删除。").verdict,
        )
        self.assertEqual(
            GuardrailVerdict.ALLOW,
            verify_business_answer([], "No order was deleted.").verdict,
        )


if __name__ == "__main__":
    unittest.main()
