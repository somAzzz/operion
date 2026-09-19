import unittest
from pathlib import Path

from pydantic_ai.messages import ModelResponse, TextPart
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


if __name__ == "__main__":
    unittest.main()
