import asyncio
import hashlib
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage
from structured_helpers import output_response

from operion_etl.agent_runtime import (
    AGENT_INSTRUCTIONS,
    AgentDependencies,
    AgentSettings,
    PendingSelection,
    check_fulfillment,
    create_operion_agent,
    get_customer_overview,
    present_answer,
    propose_followup_task,
    search_customers,
)
from operion_etl.answer_evidence import AnswerPlan, TableSelection
from operion_etl.read_tools import AccessScope, CanonicalRepository

CANONICAL = Path("tests/fixtures/wwi-small")
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
            return output_response(messages)

        settings = AgentSettings(max_model_requests=6, max_tool_calls=4)
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
            return output_response(messages)

        settings = AgentSettings()
        agent = create_operion_agent(settings, model=FunctionModel(model_function))
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID})),
            user_id="user-1",
            allowed_tools=frozenset({"get_customer_portfolio_summary"}),
        )

        result = agent.run_sync("how many customers do we have", deps=deps)

        self.assertIn("Customers (current authorized", result.output)
        self.assertIn("**1**", result.output)
        self.assertEqual("get_customer_portfolio_summary", deps.tool_calls[0]["name"])
        self.assertEqual(1, deps.tool_calls[0]["result"]["data"]["customer_count"])

    def test_ambiguous_customer_contact_question_returns_choices(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {
                        "wwi:organization:customer:11",
                        "wwi:organization:customer:150",
                    }
                ),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        result = search_customers(ctx, "Tailspin Toys", limit=10)
        self.assertEqual(2, len(result["data"]["results"]))
        self.assertEqual(
            ("wwi:organization:customer:150", "wwi:organization:customer:11"),
            deps.candidate_selection.candidate_ids,
        )
        answer = present_answer(ctx, AnswerPlan(language="en"))
        self.assertIn("Please choose", answer)
        self.assertIn("Tailspin Toys", answer)
        self.assertIn("wwi:organization:customer:11", answer)
        self.assertIn("wwi:organization:customer:150", answer)
        self.assertEqual(
            ["search_customers"], [call["name"] for call in deps.tool_calls]
        )

    def test_explicit_list_does_not_force_customer_selection(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {"wwi:organization:customer:11", "wwi:organization:customer:150"}
                ),
            ),
            user_id="user-1",
        )
        result = search_customers(
            SimpleNamespace(deps=deps), "Tailspin Toys", resolve_one=False
        )
        self.assertIsNone(deps.candidate_selection)
        table_id = result["answer_evidence"]["tables"][0]["id"]
        answer = present_answer(
            SimpleNamespace(deps=deps),
            AnswerPlan(language="en", tables=[TableSelection(table_id=table_id)]),
        )
        self.assertIn("Tailspin Toys", answer)
        self.assertIsNone(deps.candidate_selection)

    def test_list_mode_search_can_resolve_to_server_backed_clarification(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset({CUSTOMER_ID, "wwi:organization:customer:150"}),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        search_customers(ctx, "Tailspin Toys", resolve_one=False)
        self.assertIsNone(deps.candidate_selection)
        answer = present_answer(ctx, AnswerPlan(language="en", notice="needs_details"))
        self.assertIn("Please choose", answer)
        self.assertEqual("needs_selection", deps.candidate_selection.mode)
        self.assertEqual(2, len(deps.candidate_selection.candidate_ids))

    def test_list_mode_incomplete_page_only_requests_refinement(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset({CUSTOMER_ID, "wwi:organization:customer:150"}),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        search_customers(ctx, "Tailspin Toys", limit=1, resolve_one=False)
        answer = present_answer(ctx, AnswerPlan(language="en", notice="needs_details"))
        self.assertIn("More matches exist", answer)
        self.assertEqual("needs_refinement", deps.candidate_selection.mode)

    def test_list_mode_clarification_rejects_forged_reference(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset({CUSTOMER_ID, "wwi:organization:customer:150"}),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        search_customers(ctx, "Tailspin Toys", resolve_one=False)
        with self.assertRaises(ModelRetry):
            present_answer(
                ctx,
                AnswerPlan(
                    language="en",
                    notice="needs_details",
                    tables=[TableSelection(table_id="forged-table")],
                ),
            )

    def test_latest_failed_tool_sequence_completes_with_clarification(self):
        requests = 0

        async def model_function(messages, info: AgentInfo):
            nonlocal requests
            requests += 1
            if requests == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_customers",
                            {"query": "Tailspin Toys", "resolve_one": False},
                            "search",
                        )
                    ]
                )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "present_answer",
                        {"plan": {"language": "en", "notice": "needs_details"}},
                        "answer",
                    )
                ]
            )

        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset({CUSTOMER_ID, "wwi:organization:customer:150"}),
            ),
            user_id="user-1",
        )
        agent = create_operion_agent(
            AgentSettings(max_model_requests=4, max_tool_calls=2),
            model=FunctionModel(model_function),
        )
        result = asyncio.run(agent.run("Tailspin Toys contact email", deps=deps))
        self.assertIn("Please choose", result.output)
        self.assertEqual(["search_customers"], [c["name"] for c in deps.tool_calls])

    def test_partial_overview_returns_typed_ambiguity(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {"wwi:organization:customer:11", "wwi:organization:customer:150"}
                ),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        result = get_customer_overview(ctx, "Tailspin Toys")
        self.assertEqual("ambiguous_customer", result["error"]["code"])
        self.assertEqual("get_customer_overview", deps.candidate_selection.source_tool)
        answer = present_answer(ctx, AnswerPlan(language="en"))
        self.assertIn("Please choose", answer)
        self.assertIn("wwi:organization:customer:11", answer)
        self.assertIn("wwi:organization:customer:150", answer)

    def test_ambiguous_search_removes_followup_tools(self):
        async def model_function(messages, info: AgentInfo):
            return output_response(messages)

        model = FunctionModel(model_function)
        agent = create_operion_agent(
            AgentSettings(max_model_requests=4, max_tool_calls=2),
            model=model,
        )
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {"wwi:organization:customer:11", "wwi:organization:customer:150"}
                ),
            ),
            user_id="user-1",
        )
        ctx = RunContext(deps=deps, model=model, usage=RunUsage())
        toolset = agent.toolsets[-1]
        self.assertIn("get_customer_overview", asyncio.run(toolset.get_tools(ctx)))
        search_customers(ctx, "Tailspin Toys")
        self.assertEqual({}, asyncio.run(toolset.get_tools(ctx)))

    def test_same_turn_calls_are_blocked_at_execution(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {"wwi:organization:customer:11", "wwi:organization:customer:150"}
                ),
            ),
            user_id="user-1",
            proposal_service=SimpleNamespace(
                propose=lambda **_: self.fail("action ran")
            ),
        )
        ctx = SimpleNamespace(deps=deps)
        search_customers(ctx, "Tailspin Toys")
        with patch.object(
            deps.repository, "customer_overview", side_effect=AssertionError("read ran")
        ):
            with self.assertRaises(ModelRetry):
                get_customer_overview(ctx, "wwi:organization:customer:11")
        with self.assertRaises(ModelRetry):
            check_fulfillment(ctx, "F01")
        with self.assertRaises(ModelRetry):
            propose_followup_task(ctx, "F03", "title", "body", datetime.now(UTC))
        self.assertEqual(
            ["search_customers"], [call["name"] for call in deps.tool_calls]
        )

    def test_same_model_response_cannot_read_an_unselected_candidate(self):
        responses = 0

        async def model_function(messages, info: AgentInfo):
            nonlocal responses
            responses += 1
            if responses == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_customers",
                            {"query": "Tailspin Toys"},
                            "call-search",
                        ),
                        ToolCallPart(
                            "get_customer_overview",
                            {"customer": CUSTOMER_ID},
                            "call-overview",
                        ),
                    ]
                )
            return output_response(messages)

        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset({CUSTOMER_ID, "wwi:organization:customer:150"}),
            ),
            user_id="user-1",
        )
        agent = create_operion_agent(
            AgentSettings(max_model_requests=5, max_tool_calls=3),
            model=FunctionModel(model_function),
        )
        result = asyncio.run(agent.run("Find the customer", deps=deps))
        self.assertIn("Please choose", result.output)
        self.assertEqual(["search_customers"], [c["name"] for c in deps.tool_calls])

    def test_pending_selection_only_allows_selected_id_once(self):
        chosen = "wwi:organization:customer:11"
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope("AI Demo GmbH", frozenset({chosen})),
            user_id="user-1",
            pending_selection=PendingSelection(
                role="customer",
                query="Tailspin Toys",
                candidate_ids=(chosen, "wwi:organization:customer:150"),
                context_fingerprint="scope",
            ),
            selected_candidate_id=chosen,
        )
        ctx = SimpleNamespace(deps=deps)
        with self.assertRaises(ModelRetry):
            get_customer_overview(ctx, "wwi:organization:customer:150")
        result = get_customer_overview(ctx, chosen)
        self.assertTrue(result["ok"])
        with self.assertRaises(ModelRetry):
            get_customer_overview(ctx, chosen)

    def test_forged_clarification_reference_is_rejected(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {"wwi:organization:customer:11", "wwi:organization:customer:150"}
                ),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        search_customers(ctx, "Tailspin Toys")
        with self.assertRaises(ModelRetry):
            present_answer(
                ctx,
                AnswerPlan(
                    language="en",
                    tables=[TableSelection(table_id="forged-table")],
                ),
            )

    def test_incomplete_search_requires_refinement(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset(
                    {"wwi:organization:customer:11", "wwi:organization:customer:150"}
                ),
            ),
            user_id="user-1",
        )
        ctx = SimpleNamespace(deps=deps)
        search_customers(ctx, "Tailspin Toys", limit=1)
        self.assertEqual("needs_refinement", deps.candidate_selection.mode)
        self.assertIn(
            "More matches exist", present_answer(ctx, AnswerPlan(language="en"))
        )

    def test_later_search_page_cannot_become_complete_candidate_set(self):
        deps = AgentDependencies(
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope(
                "AI Demo GmbH",
                frozenset({CUSTOMER_ID, "wwi:organization:customer:150"}),
            ),
            user_id="user-1",
        )
        first = search_customers(
            SimpleNamespace(deps=deps), "Tailspin Toys", limit=1, resolve_one=False
        )
        cursor = first["data"]["pagination"]["next_cursor"]
        search_customers(
            SimpleNamespace(deps=deps),
            "Tailspin Toys",
            limit=1,
            cursor=cursor,
        )
        self.assertEqual("needs_refinement", deps.candidate_selection.mode)

    def test_tools_are_filtered_by_server_dependencies(self):
        observed_tools = []

        def model_function(messages, info: AgentInfo):
            observed_tools.append(sorted(tool.name for tool in info.function_tools))
            return output_response(messages)

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
        self.assertIn("Please specify", result.output)
        self.assertEqual([["get_customer_overview"]], observed_tools)

    def test_settings_define_bounded_model_and_tool_usage(self):
        settings = AgentSettings(
            max_model_requests=3,
            max_tool_calls=1,
            max_input_tokens=100,
            max_output_tokens=50,
            max_run_output_tokens=75,
        )
        limits = settings.usage_limits()
        self.assertEqual(3, limits.request_limit)
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
        with self.assertRaisesRegex(ValueError, "max_tool_calls \\+ 2"):
            AgentSettings(max_model_requests=3, max_tool_calls=3)
        with self.assertRaisesRegex(ValueError, "one answer repair"):
            AgentSettings(max_model_requests=7, max_tool_calls=6)
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
            return output_response(messages)

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
        self.assertIn("PENDING", result.output)
        self.assertIn("action-1", result.output)
        self.assertEqual(1, len(service.calls))
        self.assertEqual(
            "agent:" + hashlib.sha256(b"conversation-1\0run-1").hexdigest(),
            service.calls[0]["idempotency_key"],
        )
        self.assertEqual("propose_followup_task", deps.tool_calls[0]["name"])
        self.assertTrue(deps.tool_calls[0]["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
