import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from operion_etl.agent_runtime import (
    AGENT_INSTRUCTIONS,
    AgentDependencies,
    AgentSettings,
    create_operion_agent,
)
from operion_etl.read_tools import AccessScope, CanonicalRepository

CANONICAL = Path("data/canonical/wwi-v1-small-20260913-v4")
CUSTOMER_ID = "wwi:organization:customer:11"


class AgentRuntimeTests(unittest.TestCase):
    def test_instructions_only_route_tools_and_describe_conversation(self):
        for tool in (
            "get_customer_order_distribution",
            "get_organization_orders",
            "check_operation_capability",
        ):
            self.assertIn(tool, AGENT_INSTRUCTIONS)
        for rule in (
            "Picked quantity is not delivered quantity",
            "bare numeric customer source ID",
            "supplier/purchase-order context",
            "pending means pending",
            "confirmed open orders",
            "customer_order_counts",
        ):
            self.assertNotIn(rule, AGENT_INSTRUCTIONS)
        self.assertIn("latest user message", AGENT_INSTRUCTIONS)

    def test_new_typed_tools_return_server_decisions(self):
        calls = [
            ("get_customer_order_distribution", {}),
            ("get_organization_orders", {"query": "11", "relationship": "customer"}),
            ("check_operation_capability", {"operation": "business_write"}),
        ]
        count = 0

        def model_function(messages, info: AgentInfo):
            nonlocal count
            if count < len(calls):
                name, arguments = calls[count]
                count += 1
                return ModelResponse(
                    parts=[ToolCallPart(name, arguments, f"call-{count}")]
                )
            return ModelResponse(parts=[TextPart("Done.")])

        settings = AgentSettings(max_model_requests=5, max_tool_calls=4)
        agent = create_operion_agent(settings, model=FunctionModel(model_function))
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID})),
            user_id="user-1",
        )
        agent.run_sync("summarize and check capabilities", deps=deps)
        distribution, orders, capability = [
            call["result"]["data"] for call in deps.tool_calls
        ]
        self.assertEqual("complete", distribution["completeness"]["status"])
        self.assertEqual("resolved", orders["resolution"]["status"])
        self.assertEqual("authorized", orders["resolution"]["authorization"])
        self.assertEqual("denied", capability["authorization"]["status"])

    def test_customer_portfolio_summary_is_available_as_a_server_tool(self):
        call_count = 0

        def model_function(messages, info: AgentInfo):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "get_customer_portfolio_summary",
                            {},
                            "call-summary",
                        )
                    ]
                )
            return ModelResponse(parts=[TextPart("One authorized customer.")])

        settings = AgentSettings()
        agent = create_operion_agent(settings, model=FunctionModel(model_function))
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID})),
            user_id="user-1",
            allowed_tools=frozenset({"get_customer_portfolio_summary"}),
        )

        result = agent.run_sync("how many customers do we have", deps=deps)

        self.assertEqual("One authorized customer.", result.output)
        self.assertEqual("get_customer_portfolio_summary", deps.tool_calls[0]["name"])
        self.assertEqual(1, deps.tool_calls[0]["result"]["data"]["customer_count"])

    def test_tools_are_filtered_by_server_dependencies(self):
        observed_tools = []

        def model_function(messages, info: AgentInfo):
            observed_tools.append(sorted(tool.name for tool in info.function_tools))
            return ModelResponse(parts=[TextPart("done")])

        settings = AgentSettings()
        agent = create_operion_agent(settings, model=FunctionModel(model_function))
        repository = CanonicalRepository(CANONICAL)
        deps = AgentDependencies(
            repository=repository,
            scope=AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID})),
            user_id="user-1",
            allowed_tools=frozenset({"get_customer_overview"}),
        )
        result = agent.run_sync("overview", deps=deps)
        self.assertEqual("done", result.output)
        self.assertEqual([["get_customer_overview"]], observed_tools)

    def test_settings_define_bounded_model_and_tool_usage(self):
        settings = AgentSettings(
            max_model_requests=2,
            max_tool_calls=1,
            max_input_tokens=100,
            max_output_tokens=50,
            max_run_output_tokens=75,
        )
        limits = settings.usage_limits()
        self.assertEqual(2, limits.request_limit)
        self.assertEqual(1, limits.tool_calls_limit)
        self.assertEqual(100, limits.input_tokens_limit)
        self.assertEqual(75, limits.output_tokens_limit)
        self.assertEqual(50, settings.model_settings()["max_tokens"])

    def test_settings_read_explicit_interview_token_budgets(self):
        with patch.dict(
            os.environ,
            {
                "OPERION_MAX_INPUT_TOKENS": "40000",
                "OPERION_MAX_OUTPUT_TOKENS": "3000",
                "OPERION_MAX_RUN_OUTPUT_TOKENS": "9000",
            },
        ):
            settings = AgentSettings.from_environment()

        self.assertEqual(40_000, settings.max_input_tokens)
        self.assertEqual(3_000, settings.max_output_tokens)
        self.assertEqual(9_000, settings.max_run_output_tokens)
        self.assertEqual(40_000, settings.usage_limits().input_tokens_limit)
        self.assertEqual(9_000, settings.usage_limits().output_tokens_limit)
        self.assertEqual(3_000, settings.model_settings()["max_tokens"])

    def test_settings_reject_inconsistent_request_and_output_budgets(self):
        with self.assertRaisesRegex(ValueError, "must exceed max_tool_calls"):
            AgentSettings(max_model_requests=3, max_tool_calls=3)
        with self.assertRaisesRegex(ValueError, "at least max_output_tokens"):
            AgentSettings(max_output_tokens=100, max_run_output_tokens=99)

    def test_followup_tool_only_creates_a_server_side_proposal(self):
        class FakeProposalService:
            calls = []

            def propose(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "action_id": "action-1",
                    "current_revision": 1,
                    "state": "PENDING_APPROVAL",
                    "expires_at": "2026-09-20T13:00:00Z",
                    "payload_json": {
                        "target": {"order_id": "SO-1"},
                        "parameters": {"title": kwargs["title"]},
                        "side_effects": ["twenty_internal_task"],
                    },
                }

        call_count = 0

        def model_function(messages, info: AgentInfo):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "propose_followup_task",
                            {
                                "case_id": "F03",
                                "title": "Review shortfall",
                                "body": "Inspect the evidence.",
                                "due_at": "2026-09-22T12:00:00+00:00",
                            },
                            "call-1",
                        )
                    ]
                )
            return ModelResponse(parts=[TextPart("Proposal saved for approval.")])

        service = FakeProposalService()
        settings = AgentSettings()
        agent = create_operion_agent(settings, model=FunctionModel(model_function))
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID})),
            user_id="requester",
            allowed_tools=frozenset({"propose_followup_task"}),
            proposal_service=service,
            conversation_id="conversation-1",
            run_id="run-1",
        )
        result = agent.run_sync("propose", deps=deps)
        self.assertEqual("Proposal saved for approval.", result.output)
        self.assertEqual(1, len(service.calls))
        self.assertEqual(
            "agent:" + hashlib.sha256(b"conversation-1\0run-1").hexdigest(),
            service.calls[0]["idempotency_key"],
        )
        self.assertEqual("propose_followup_task", deps.tool_calls[0]["name"])
        self.assertTrue(deps.tool_calls[0]["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
