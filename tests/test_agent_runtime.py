import hashlib
import unittest
from pathlib import Path

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from operion_etl.agent_runtime import (
    AgentDependencies,
    AgentSettings,
    create_operion_agent,
)
from operion_etl.read_tools import AccessScope, CanonicalRepository

CANONICAL = Path("data/canonical/wwi-v1-small-20260913-v4")
CUSTOMER_ID = "wwi:organization:customer:11"


class AgentRuntimeTests(unittest.TestCase):
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
        )
        limits = settings.usage_limits()
        self.assertEqual(2, limits.request_limit)
        self.assertEqual(1, limits.tool_calls_limit)
        self.assertEqual(100, limits.input_tokens_limit)
        self.assertEqual(50, limits.output_tokens_limit)

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
