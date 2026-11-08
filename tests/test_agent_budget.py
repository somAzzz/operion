"""Budget regressions use the real runtime with a deterministic offline model."""

import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.usage import RunUsage
from structured_helpers import output_response

from operion_etl.agent_app import AgentApplication, create_app
from operion_etl.agent_budget import DiagnosedUsageLimits
from operion_etl.agent_runtime import (
    AgentDependencies,
    AgentSettings,
    create_operion_agent,
)
from operion_etl.read_tools import AccessScope, CanonicalRepository
from operion_etl.session_store import ConversationStore


class AnswerBudgetTests(unittest.TestCase):
    def test_default_and_environment_budgets_reserve_answer_repair(self):
        with patch.dict(os.environ, {}, clear=True):
            for settings in (AgentSettings(), AgentSettings.from_environment()):
                self.assertEqual(6, settings.max_tool_calls)
                self.assertEqual(8, settings.max_model_requests)

    def test_configured_six_tools_and_one_answer_repair_finish(self):
        configured = dict(
            line.split("=", 1)
            for line in Path("config/demo/wwi-snapshot.env")
            .read_text()
            .splitlines()
            if line.startswith("OPERION_MAX_")
        )
        with patch.dict(os.environ, configured, clear=True):
            settings = AgentSettings.from_environment()
        requests = 0
        valid_answer = None

        async def model(messages, info):
            nonlocal requests, valid_answer
            requests += 1
            if requests <= 6:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "get_customer_portfolio_summary", {}, f"call-{requests}"
                        )
                    ]
                )
            if requests == 7:
                valid_answer = output_response(messages, field="customer_count")
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "present_answer",
                            {"plan": {"language": "en", "facts": ["forged-reference"]}},
                            "invalid-answer",
                        )
                    ]
                )
            return valid_answer

        deps = AgentDependencies(
            repository=CanonicalRepository(Path("tests/fixtures/wwi-small")),
            scope=AccessScope(
                "AI Demo GmbH", frozenset({"wwi:organization:customer:11"})
            ),
            user_id="budget-test",
        )
        agent = create_operion_agent(settings, model=FunctionModel(model))
        result = agent.run_sync(
            "How many customers?", deps=deps, usage_limits=settings.usage_limits()
        )
        self.assertEqual(8, result.usage.requests)
        self.assertEqual(6, result.usage.tool_calls)
        self.assertEqual(6, len(deps.tool_calls))
        self.assertIn("**1**", result.output)
        self.assertNotIn("forged-reference", result.output)


class BudgetDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.temp.name) / "sessions.sqlite3")
        self.settings = AgentSettings(
            max_input_tokens=100_000,
            max_output_tokens=4000,
            max_run_output_tokens=12_000,
            run_timeout_seconds=5,
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_model(self, model, settings=None):
        settings = settings or self.settings
        if model.stream_function is None:

            async def stream(messages, info):
                response = await model.function(messages, info)
                for index, part in enumerate(response.parts):
                    if isinstance(part, ToolCallPart):
                        yield {
                            index: DeltaToolCall(
                                name=part.tool_name,
                                json_args=part.args_as_json_str(),
                                tool_call_id=part.tool_call_id,
                            )
                        }
                    else:
                        yield part.content

            model.stream_function = stream
        application = AgentApplication(
            settings=settings,
            repository=CanonicalRepository(Path("tests/fixtures/wwi-small")),
            scope=AccessScope(
                "AI Demo GmbH", frozenset({"wwi:organization:customer:11"})
            ),
            store=self.store,
            token="test-token",
            user_id="budget-user",
            agent=create_operion_agent(settings, model=model),
        )
        with TestClient(create_app(application)) as client:
            response = client.post(
                "/api/agent",
                json={
                    "threadId": "budget-thread",
                    "runId": "budget-run",
                    "state": {},
                    "context": [],
                    "forwardedProps": {},
                    "tools": [],
                    "messages": [
                        {"id": "user", "role": "user", "content": "PRIVATE_PROMPT"}
                    ],
                },
                headers={
                    "Authorization": "Bearer test-token",
                    "Accept": "text/event-stream",
                },
            )
        self.assertEqual(200, response.status_code)
        row = self.store.run("budget-run", "budget-user")
        self.assertNotIn("PRIVATE_PROMPT", json.dumps(row["budget"]))
        return response, row

    def assert_failed_budget(self, response, row, kind):
        self.assertIn("LIMIT_EXCEEDED", response.text)
        self.assertNotIn("RUN_FINISHED", response.text)
        self.assertNotIn("TEXT_MESSAGE_CONTENT", response.text)
        self.assertNotIn("tool_calls_limit", response.text)
        self.assertNotIn("request_limit", response.text)
        self.assertNotIn('budget"', response.text)
        self.assertEqual("failed", row["status"])
        self.assertEqual("LIMIT_EXCEEDED", row["error_code"])
        self.assertEqual(kind, row["budget"]["exceeded"]["kind"])
        self.assertEqual([], self.store.public_history("budget-thread", "budget-user"))

    def test_seventh_tool_is_blocked_and_usage_is_retained(self):
        async def model(messages, info):
            return ModelResponse(
                parts=[ToolCallPart("get_customer_portfolio_summary", {})],
            )

        response, row = self.run_model(FunctionModel(model))
        self.assert_failed_budget(response, row, "tool_calls")
        self.assertEqual(6, len(row["tool_calls"]))
        self.assertEqual(
            {"kind": "tool_calls", "used": 6, "limit": 6, "attempted": 7},
            row["budget"]["exceeded"],
        )
        self.assertEqual(7, row["budget"]["usage"]["model_requests"])
        self.assertGreater(row["input_tokens"], 0)
        self.assertGreater(row["output_tokens"], 0)
        self.assertEqual(row["input_tokens"], row["budget"]["usage"]["input_tokens"])
        self.assertEqual(row["output_tokens"], row["budget"]["usage"]["output_tokens"])

    def test_repaired_answer_is_published_and_saved_with_success_usage(self):
        requests = 0
        valid_answer = None

        async def model(messages, info):
            nonlocal requests, valid_answer
            requests += 1
            if requests <= 6:
                return ModelResponse(
                    parts=[ToolCallPart("get_customer_portfolio_summary", {})]
                )
            if requests == 7:
                valid_answer = output_response(messages, field="customer_count")
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "present_answer",
                            {
                                "plan": {
                                    "language": "en",
                                    "facts": ["PRIVATE_FAKE_REFERENCE"],
                                }
                            },
                        )
                    ]
                )
            return valid_answer

        response, row = self.run_model(FunctionModel(model))
        self.assertIn("RUN_FINISHED", response.text)
        self.assertNotIn("RUN_ERROR", response.text)
        self.assertNotIn("PRIVATE_FAKE_REFERENCE", response.text)
        self.assertEqual("succeeded", row["status"])
        self.assertIsNone(row["budget"]["exceeded"])
        self.assertEqual(8, row["budget"]["usage"]["model_requests"])
        self.assertEqual(6, row["budget"]["usage"]["tool_calls"])
        self.assertGreater(row["input_tokens"], 0)
        history = self.store.public_history("budget-thread", "budget-user")
        self.assertIn("**1**", history[-1]["content"])
        self.assertNotIn("PRIVATE_FAKE_REFERENCE", json.dumps(history))

    def test_over_budget_batch_is_rejected_before_execution(self):
        async def model(messages, info):
            return ModelResponse(
                parts=[
                    ToolCallPart("get_customer_portfolio_summary", {}, f"call-{i}")
                    for i in range(7)
                ]
            )

        response, row = self.run_model(FunctionModel(model))
        self.assert_failed_budget(response, row, "tool_calls")
        self.assertEqual([], row["tool_calls"])
        self.assertEqual(0, row["budget"]["exceeded"]["used"])
        self.assertEqual(7, row["budget"]["exceeded"]["attempted"])

    def test_request_limit_after_guardrail_rejection_keeps_true_cause(self):
        requests = 0

        async def model(messages, info):
            nonlocal requests
            requests += 1
            if requests == 1:
                # One schema retry consumes a request but executes no tool.
                call = ToolCallPart(
                    "get_customer_portfolio_summary", {"customer": "invalid"}
                )
            elif requests <= 7:
                call = ToolCallPart("get_customer_portfolio_summary", {})
            else:
                call = ToolCallPart(
                    "present_answer",
                    {"plan": {"language": "en", "facts": ["PRIVATE_FAKE_REFERENCE"]}},
                )
            return ModelResponse(parts=[call])

        response, row = self.run_model(FunctionModel(model))
        self.assert_failed_budget(response, row, "model_requests")
        self.assertEqual(8, requests)
        self.assertEqual(6, len(row["tool_calls"]))
        self.assertEqual(
            {"kind": "model_requests", "used": 8, "limit": 8, "attempted": 9},
            row["budget"]["exceeded"],
        )
        self.assertGreater(row["input_tokens"], 0)
        self.assertGreater(row["output_tokens"], 0)
        self.assertNotIn("PRIVATE_FAKE_REFERENCE", response.text)
        self.assertNotIn("PRIVATE_FAKE_REFERENCE", json.dumps(row["budget"]))

    def test_input_tokens_are_diagnosed(self):
        async def model(messages, info):
            return ModelResponse(parts=[TextPart("unpublished private model text")])

        response, row = self.run_model(
            FunctionModel(model), replace(self.settings, max_input_tokens=1)
        )
        self.assert_failed_budget(response, row, "input_tokens")
        self.assertGreater(row["input_tokens"], 1)
        self.assertEqual(row["input_tokens"], row["budget"]["exceeded"]["used"])
        self.assertEqual(1, row["budget"]["exceeded"]["limit"])

    def test_output_tokens_are_diagnosed(self):
        async def model(messages, info):
            return ModelResponse(parts=[TextPart("unpublished private model text")])

        response, row = self.run_model(
            FunctionModel(model),
            replace(self.settings, max_output_tokens=1, max_run_output_tokens=1),
        )
        self.assert_failed_budget(response, row, "output_tokens")
        self.assertGreater(row["input_tokens"], 0)
        self.assertGreater(row["output_tokens"], 1)
        self.assertEqual(row["output_tokens"], row["budget"]["exceeded"]["used"])
        self.assertEqual(1, row["budget"]["exceeded"]["limit"])

    def test_deadline_keeps_usage_and_content_free_trace(self):
        requests = 0

        async def stream(messages, info):
            nonlocal requests
            requests += 1
            if requests == 1:
                yield {
                    0: DeltaToolCall(
                        name="get_customer_portfolio_summary",
                        json_args="{}",
                        tool_call_id="first",
                    )
                }
            else:
                await asyncio.sleep(1)
                yield "too late"

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        try:
            with patch(
                "operion_etl.agent_app.trace.get_tracer",
                return_value=provider.get_tracer("budget-test"),
            ):
                response, row = self.run_model(
                    FunctionModel(stream_function=stream),
                    replace(self.settings, run_timeout_seconds=0.1),
                )
            self.assert_failed_budget(response, row, "deadline")
            self.assertEqual(1, row["budget"]["usage"]["tool_calls"])
            self.assertGreater(row["input_tokens"], 0)
            self.assertGreater(row["output_tokens"], 0)
            self.assertGreaterEqual(row["budget"]["exceeded"]["used"], 0.1)
            run = next(
                s
                for s in exporter.get_finished_spans()
                if s.name == "operion.agent.run"
            )
            self.assertEqual("deadline", run.attributes["operion.budget.exceeded.kind"])
            self.assertEqual(6, run.attributes["operion.budget.limit.tool_calls"])
            self.assertNotIn("PRIVATE_PROMPT", repr(run.attributes))
        finally:
            provider.shutdown()

    def test_upstream_timeout_is_not_a_run_deadline(self):
        async def model(messages, info):
            raise TimeoutError("PRIVATE_UPSTREAM_DETAIL")

        response, row = self.run_model(FunctionModel(model))
        self.assertNotIn("LIMIT_EXCEEDED", response.text)
        self.assertNotIn("PRIVATE_UPSTREAM_DETAIL", response.text)
        self.assertIsNone(row["budget"]["exceeded"])

    def test_provisional_stream_tokens_survive_before_usage_commit(self):
        limits = DiagnosedUsageLimits(input_tokens_limit=100)
        with self.assertRaises(UsageLimitExceeded):
            limits.check_tokens(RunUsage(input_tokens=101, output_tokens=7))
        self.assertEqual(0, limits.usage.input_tokens)
        snapshot = limits.snapshot(0.1, 90)
        self.assertEqual(101, snapshot["usage"]["input_tokens"])
        self.assertEqual(7, snapshot["usage"]["output_tokens"])
        self.assertEqual("input_tokens", snapshot["exceeded"]["kind"])
