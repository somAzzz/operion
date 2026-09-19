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

    def test_detects_forbidden_nested_field(self):
        case = {
            "tool": "get_customer_overview",
            "forbidden_output_fields": ["email"],
        }
        calls = [
            {
                "name": "get_customer_overview",
                "result": {"ok": True, "data": {"contact": {"email": "x"}}},
            }
        ]
        self.assertEqual(
            ["forbidden_field_exposed"], grade_case(case, calls, "没有敏感字段。")
        )


if __name__ == "__main__":
    unittest.main()
