"""Evaluation grades the emitted structured facts and exact renderer output."""

import unittest

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from structured_helpers import output_response
from test_business_fact_binding import add, orders, registry

from operion_etl.agent_runtime import (
    AgentDependencies,
    AgentSettings,
    create_operion_agent,
)
from operion_etl.answer_evidence import AnswerPlan
from operion_etl.e2_evaluation import UnavailableRepository, grade_case
from operion_etl.read_tools import AccessScope


class E2EvaluationTests(unittest.TestCase):
    def test_correct_tool_does_not_pass_if_final_answer_is_unsupported(self):
        reg = registry()
        data = orders()
        evidence = add(reg, "list_sales_orders", data)
        calls = [{"name": "list_sales_orders", "result": {"ok": True, "data": data}}]
        ref = next(
            f["id"] for f in evidence["facts"] if f["field"] == "sales_order_count"
        )
        plan = AnswerPlan(language="en", facts=[ref])
        self.assertEqual(
            [],
            grade_case(
                {"tool": "list_sales_orders"},
                calls,
                reg.render(plan),
                registry=reg,
                plan=plan,
            ),
        )
        self.assertIn(
            "answer_render_mismatch",
            grade_case(
                {"tool": "list_sales_orders"},
                calls,
                "There are 999 sales orders.",
                registry=reg,
                plan=plan,
            ),
        )
        self.assertIn(
            "structured_answer_missing",
            grade_case(
                {"tool": "list_sales_orders"}, calls, "There are 30 sales orders."
            ),
        )

    def test_a_page_count_cannot_satisfy_a_total_count_gold(self):
        reg = registry()
        data = {
            "contract_version": "customer-overview-v2",
            "customer": {"canonical_id": "wwi:organization:customer:1"},
            "order_count": 30,
            "orders": [],
        }
        evidence = add(reg, "get_customer_overview", data)
        calls = [
            {"name": "get_customer_overview", "result": {"ok": True, "data": data}}
        ]
        case = {
            "tool": "get_customer_overview",
            "expected": {
                "customer_id": "wwi:organization:customer:1",
                "order_count": 30,
            },
        }
        for field, good in [("sales_order_count", True), ("page_order_count", False)]:
            ref = next(f["id"] for f in evidence["facts"] if f["field"] == field)
            plan = AnswerPlan(language="en", facts=[ref])
            failures = grade_case(
                case, calls, reg.render(plan), registry=reg, plan=plan
            )
            self.assertEqual(good, not failures)
            if not good:
                self.assertIn("answer_missing_order_count", failures)

    def test_fulfillment_result_must_be_selected_not_merely_fetched(self):
        reg = registry()
        data = {
            "contract_version": "fulfillment-v1",
            "data_mode": "snapshot",
            "case_id": "F01",
            "result": "shortfall",
        }
        evidence = add(reg, "check_fulfillment", data)
        calls = [{"name": "check_fulfillment", "result": {"ok": True, "data": data}}]
        case = {"tool": "check_fulfillment", "expected_result": "shortfall"}
        for field, good in [("result", True), ("case_id", False)]:
            ref = next(f["id"] for f in evidence["facts"] if f["field"] == field)
            plan = AnswerPlan(language="en", facts=[ref])
            self.assertEqual(
                good,
                not grade_case(case, calls, reg.render(plan), registry=reg, plan=plan),
            )

    def test_tool_selection_arguments_and_forbidden_fields_still_checked(self):
        reg = registry()
        plan = AnswerPlan(language="en", notice="needs_details")
        calls = [
            {
                "name": "get_customer_overview",
                "arguments": {"customer": "wrong"},
                "result": {"ok": True, "data": {"customer": {"credit_limit": 1}}},
            }
        ]
        failures = grade_case(
            {
                "tool": "get_customer_overview",
                "expected_arguments": {"customer": "right"},
                "forbidden_output_fields": ["credit_limit"],
            },
            calls,
            reg.render(plan),
            registry=reg,
            plan=plan,
        )
        self.assertIn("wrong_tool_arguments", failures)
        self.assertIn("forbidden_field_exposed", failures)
        self.assertEqual(
            ["expected_tool_not_called"],
            grade_case({"tool": "get_customer_overview"}, [], ""),
        )
        self.assertIn(
            "unexpected_tool_call", grade_case({"expected_tool_call": None}, calls, "")
        )

    def test_unavailable_repository_returns_tool_error_to_agent(self):
        count = 0

        def model_function(messages, info):
            nonlocal count
            count += 1
            if count == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "get_customer_overview", {"customer": "customer-a"}, "read"
                        )
                    ]
                )
            return output_response(messages, language="zh")

        agent = create_operion_agent(
            AgentSettings(), model=FunctionModel(model_function)
        )
        deps = AgentDependencies(
            repository=UnavailableRepository(),
            scope=AccessScope("Synthetic Co", frozenset({"customer-a"})),
            user_id="e2-evaluator",
        )
        result = agent.run_sync("概览客户 A", deps=deps)
        self.assertIn("结果未知", result.output)
        self.assertEqual(
            "source_unavailable", deps.tool_calls[0]["result"]["error"]["code"]
        )


if __name__ == "__main__":
    unittest.main()
