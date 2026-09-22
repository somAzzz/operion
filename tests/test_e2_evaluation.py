import unittest

from operion_etl.e2_evaluation import grade_case


class E2EvaluationTests(unittest.TestCase):
    def test_grades_fulfillment_evidence(self):
        case = {
            "tool": "check_fulfillment",
            "expected_result": "shortfall",
            "required_source": "source-1",
        }
        calls = [
            {
                "name": "check_fulfillment",
                "result": {
                    "ok": True,
                    "data": {"result": "shortfall", "sources": ["source-1"]},
                },
            }
        ]
        self.assertEqual([], grade_case(case, calls, "库存不足。"))

    def test_rejects_unexpected_write_tool(self):
        case = {"expected_tool_call": None}
        calls = [{"name": "delete_customer", "result": {"ok": True}}]
        self.assertEqual(["unexpected_tool_call"], grade_case(case, calls, "完成。"))

    def test_contact_case_requires_overview_but_allows_email_and_phone(self):
        case = {
            "tool": "get_customer_overview",
            "forbidden_output_fields": ["credit_limit", "payment_days"],
        }
        self.assertEqual(
            ["expected_tool_not_called"],
            grade_case(case, [], "No contact details were available."),
        )
        calls = [
            {
                "name": "get_customer_overview",
                "result": {
                    "ok": True,
                    "data": {
                        "contacts": [
                            {"email": "sample@example.invalid", "phone": "555-0100"}
                        ]
                    },
                },
            }
        ]
        self.assertEqual([], grade_case(case, calls, "Contact details are available."))

    def test_detects_forbidden_nested_field(self):
        case = {
            "tool": "get_customer_overview",
            "forbidden_output_fields": ["credit_limit"],
        }
        calls = [
            {
                "name": "get_customer_overview",
                "result": {"ok": True, "data": {"customer": {"credit_limit": "x"}}},
            }
        ]
        self.assertEqual(
            ["forbidden_field_exposed"], grade_case(case, calls, "没有敏感字段。")
        )


if __name__ == "__main__":
    unittest.main()
