"""Acceptance checks for the content-free Agent trace boundary."""

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings
from structured_helpers import output_delta

from operion_etl.agent_app import AgentApplication, create_app
from operion_etl.agent_runtime import AgentSettings, create_operion_agent
from operion_etl.observability import instrument_fastapi
from operion_etl.output_guardrails import (
    GuardrailDecision,
    GuardrailVerdict,
    record_guardrail,
)
from operion_etl.read_tools import AccessScope, CanonicalRepository
from operion_etl.session_store import ConversationStore


class ObservabilityTests(unittest.TestCase):
    def test_guardrail_is_child_observation_with_content_free_reason(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("operion.guardrails-test")
        try:
            with patch(
                "operion_etl.output_guardrails.trace.get_tracer", return_value=tracer
            ):
                with tracer.start_as_current_span("request") as parent:
                    record_guardrail(
                        GuardrailDecision(
                            "output_facts",
                            GuardrailVerdict.DENY,
                            "ORDER_COUNT_MISMATCH",
                        )
                    )
            child = next(
                span
                for span in exporter.get_finished_spans()
                if span.name == "operion.guardrail.output_facts"
            )
            self.assertEqual(parent.context.span_id, child.parent.span_id)
            self.assertEqual("guardrail", child.attributes["langfuse.observation.type"])
            self.assertEqual(
                "ORDER_COUNT_MISMATCH",
                child.attributes["langfuse.observation.metadata.reason_code"],
            )
            self.assertNotIn("customer", repr(child.attributes))
        finally:
            provider.shutdown()

    def test_httpx2_model_client_emits_span_without_secret_headers_or_body(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        async def exercise():
            client = httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    lambda _: httpx2.Response(200, json={"ok": True})
                )
            )
            HTTPX2ClientInstrumentor.instrument_client(client, tracer_provider=provider)
            try:
                await client.post(
                    "http://model.test/v1/chat/completions",
                    headers={"Authorization": "Bearer model-secret-marker"},
                    json={"prompt": "prompt-secret-marker"},
                )
            finally:
                await client.aclose()

        asyncio.run(exercise())
        spans = exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        self.assertNotIn("model-secret-marker", repr(spans))
        self.assertNotIn("prompt-secret-marker", repr(spans))
        provider.shutdown()

    def test_fastapi_extracts_w3c_parent_context(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        app = FastAPI()

        @app.get("/trace-check")
        def trace_check():
            context = trace.get_current_span().get_span_context()
            return {"trace_id": f"{context.trace_id:032x}"}

        instrument_fastapi(app, provider)
        parent_trace_id = "a" * 32
        parent_span_id = "b" * 16
        with TestClient(app) as client:
            response = client.get(
                "/trace-check",
                headers={"traceparent": f"00-{parent_trace_id}-{parent_span_id}-01"},
            )
        self.assertEqual(parent_trace_id, response.json()["trace_id"])
        server_span = next(
            span for span in exporter.get_finished_spans() if span.kind.name == "SERVER"
        )
        self.assertEqual(int(parent_span_id, 16), server_span.parent.span_id)
        self.assertFalse(
            any(
                span.name.endswith(("http send", "http receive"))
                for span in exporter.get_finished_spans()
            )
        )
        provider.shutdown()

    def test_existing_sqlite_run_table_migrates_without_losing_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("""
                    CREATE TABLE agent_runs (
                        run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                        owner_id TEXT NOT NULL, model_name TEXT NOT NULL,
                        status TEXT NOT NULL, tool_calls_json TEXT NOT NULL DEFAULT '[]',
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        error_code TEXT, started_at TEXT NOT NULL, completed_at TEXT
                    )
                """)
            store = ConversationStore(path)
            store.get_or_create("conversation", "owner")
            store.start_run(
                "run",
                "conversation",
                "owner",
                "model",
                trace_id="a" * 32,
                span_id="b" * 16,
            )
            self.assertEqual("a" * 32, store.run("run", "owner")["trace_id"])

    def test_run_and_model_spans_are_linked_without_prompt_content(self):
        marker = "SECRET_CUSTOMER_PROMPT_123"
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        Agent.instrument_all(
            InstrumentationSettings(
                tracer_provider=provider,
                include_content=False,
                include_binary_content=False,
                include_model_request_parameters=False,
            )
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                settings = AgentSettings(run_timeout_seconds=5)

                async def respond(messages, info):
                    yield output_delta(messages)

                agent = create_operion_agent(
                    settings, model=FunctionModel(stream_function=respond)
                )
                store = ConversationStore(Path(directory) / "sessions.sqlite3")
                application = AgentApplication(
                    settings=settings,
                    repository=CanonicalRepository(Path("tests/fixtures/wwi-small")),
                    scope=AccessScope(
                        "AI Demo GmbH", frozenset({"wwi:organization:customer:11"})
                    ),
                    store=store,
                    token="test-token",
                    user_id="user-1",
                    agent=agent,
                )
                with (
                    patch(
                        "operion_etl.agent_app.trace.get_tracer",
                        return_value=provider.get_tracer("operion.agent"),
                    ),
                    TestClient(create_app(application)) as client,
                ):
                    response = client.post(
                        "/api/agent",
                        json={
                            "threadId": "traced-conversation",
                            "runId": "traced-run",
                            "state": {},
                            "context": [],
                            "forwardedProps": {},
                            "tools": [],
                            "messages": [
                                {"id": "user-1", "role": "user", "content": marker}
                            ],
                        },
                        headers={
                            "Authorization": "Bearer test-token",
                            "Accept": "text/event-stream",
                        },
                    )
                self.assertEqual(200, response.status_code)
                self.assertIn("Please specify", response.text)
                spans = exporter.get_finished_spans()
                run = next(span for span in spans if span.name == "operion.agent.run")
                self.assertEqual("succeeded", run.attributes["operion.run.status"])
                self.assertEqual("OK", run.status.status_code.name)
                self.assertGreaterEqual(run.attributes["operion.run.first_sse_ms"], 0)
                self.assertTrue(
                    any(
                        span.parent and span.parent.span_id == run.context.span_id
                        for span in spans
                        if span is not run
                    )
                )
                self.assertNotIn(marker, repr(spans))
                stored = store.run("traced-run", "user-1")
                self.assertEqual(f"{run.context.trace_id:032x}", stored["trace_id"])
                self.assertEqual(f"{run.context.span_id:016x}", stored["span_id"])
        finally:
            Agent.instrument_all(False)
            provider.shutdown()

    def test_timed_out_stream_ends_run_span_without_prompt_content(self):
        marker = "SECRET_TIMEOUT_PROMPT_123"
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        try:
            with tempfile.TemporaryDirectory() as directory:
                settings = AgentSettings(run_timeout_seconds=0.01)

                async def slow_response(messages, info):
                    await asyncio.sleep(0.1)
                    yield "too late"

                agent = create_operion_agent(
                    settings, model=FunctionModel(stream_function=slow_response)
                )
                store = ConversationStore(Path(directory) / "sessions.sqlite3")
                application = AgentApplication(
                    settings=settings,
                    repository=CanonicalRepository(Path("tests/fixtures/wwi-small")),
                    scope=AccessScope(
                        "AI Demo GmbH", frozenset({"wwi:organization:customer:11"})
                    ),
                    store=store,
                    token="test-token",
                    user_id="user-1",
                    agent=agent,
                )
                with (
                    patch(
                        "operion_etl.agent_app.trace.get_tracer",
                        return_value=provider.get_tracer("operion.agent"),
                    ),
                    TestClient(create_app(application)) as client,
                ):
                    response = client.post(
                        "/api/agent",
                        json={
                            "threadId": "timeout-conversation",
                            "runId": "timeout-run",
                            "state": {},
                            "context": [],
                            "forwardedProps": {},
                            "tools": [],
                            "messages": [
                                {"id": "user-1", "role": "user", "content": marker}
                            ],
                        },
                        headers={
                            "Authorization": "Bearer test-token",
                            "Accept": "text/event-stream",
                        },
                    )
                self.assertEqual(200, response.status_code)
                self.assertIn("LIMIT_EXCEEDED", response.text)
                run = next(
                    span
                    for span in exporter.get_finished_spans()
                    if span.name == "operion.agent.run"
                )
                self.assertEqual("timeout", run.attributes["operion.run.status"])
                self.assertEqual("ERROR", run.status.status_code.name)
                self.assertEqual("ERROR", run.attributes["langfuse.observation.level"])
                self.assertEqual("failed", store.run("timeout-run", "user-1")["status"])
                self.assertNotIn(marker, repr(exporter.get_finished_spans()))
        finally:
            provider.shutdown()


if __name__ == "__main__":
    unittest.main()
