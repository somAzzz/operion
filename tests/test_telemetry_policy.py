"""Checks for outcome semantics, opt-in model content, and release labels."""

import asyncio
import os
import unittest
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from operion_etl.observability import (
    configure_observability,
    record_run_status,
    record_tool_result,
)


class TelemetryPolicyTests(unittest.TestCase):
    def test_business_outcomes_are_not_all_technical_errors(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        expected = {
            "succeeded": ("OK", "DEFAULT"),
            "failed": ("ERROR", "ERROR"),
            "timeout": ("ERROR", "ERROR"),
            "error": ("ERROR", "ERROR"),
            "cancelled": ("UNSET", "DEFAULT"),
            "blocked": ("UNSET", "WARNING"),
            "denied": ("UNSET", "WARNING"),
            "rejected": ("UNSET", "WARNING"),
        }
        try:
            for outcome, (status, level) in expected.items():
                with provider.get_tracer("test").start_as_current_span("run") as span:
                    record_run_status(span, outcome)
                actual = exporter.get_finished_spans()[-1]
                self.assertEqual(actual.status.status_code.name, status)
                self.assertEqual(actual.attributes["langfuse.observation.level"], level)
                self.assertEqual(
                    actual.attributes["langfuse.observation.metadata.run_status"],
                    outcome,
                )
        finally:
            provider.shutdown()

    def test_tool_expected_refusals_differ_from_upstream_errors(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        try:
            for outcome in [
                "scope_denied",
                "not_found",
                "source_unavailable",
                "internal_error",
                "success",
            ]:
                with provider.get_tracer("test").start_as_current_span("tool") as span:
                    record_tool_result(span, outcome)
                actual = exporter.get_finished_spans()[-1]
                self.assertEqual(
                    actual.status.status_code.name == "ERROR",
                    outcome in {"source_unavailable", "internal_error"},
                )
        finally:
            provider.shutdown()

    def test_content_is_opt_in_and_release_labels_reach_model_spans(self):
        for enabled in ["0", "1"]:
            exporter = InMemorySpanExporter()
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPERION_OTEL_ENABLED": "1",
                        "OPERION_OTEL_INCLUDE_CONTENT": enabled,
                        "OPERION_ENVIRONMENT": "enterprise",
                        "OPERION_TELEMETRY_ENVIRONMENT": "development",
                        "OPERION_RELEASE_ID": "test-build-42",
                    },
                ),
                patch("opentelemetry.trace.set_tracer_provider"),
                patch(
                    "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
                    return_value=exporter,
                ),
            ):
                provider = configure_observability("test", agent=True)
                try:
                    model = FunctionModel(
                        lambda messages, info: ModelResponse(
                            parts=[TextPart("RESPONSE_CONTENT_MARKER")]
                        )
                    )
                    asyncio.run(Agent(model).run("PROMPT_CONTENT_MARKER"))
                    provider.force_flush()
                    spans = exporter.get_finished_spans()
                    serialized = repr([dict(s.attributes) for s in spans])
                    self.assertEqual(
                        "PROMPT_CONTENT_MARKER" in serialized, enabled == "1"
                    )
                    self.assertEqual(
                        "RESPONSE_CONTENT_MARKER" in serialized, enabled == "1"
                    )
                    self.assertTrue(spans)
                    for span in spans:
                        self.assertEqual(
                            span.attributes["langfuse.environment"], "development"
                        )
                        self.assertEqual(
                            span.attributes["langfuse.version"], "test-build-42"
                        )
                        self.assertEqual(
                            span.resource.attributes["service.version"], "test-build-42"
                        )
                finally:
                    Agent.instrument_all(False)
                    provider.shutdown()
