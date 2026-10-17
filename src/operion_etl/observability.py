"""Optional OpenTelemetry tracing with explicitly enabled development content."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode


def content_capture_enabled() -> bool:
    return os.environ.get("OPERION_OTEL_INCLUDE_CONTENT") == "1"


def record_run_status(span: Span, status: str) -> None:
    """Keep business outcomes separate from technical failures and policy blocks."""
    span.set_attribute("operion.run.status", status)
    span.set_attribute("langfuse.observation.metadata.run_status", status)
    technical_error = status in {"error", "failed", "timeout"}
    level = (
        "ERROR"
        if technical_error
        else ("WARNING" if status in {"denied", "rejected", "blocked"} else "DEFAULT")
    )
    span.set_attribute("langfuse.observation.level", level)
    span.set_attribute("langfuse.observation.status_message", status)
    if technical_error:
        span.set_status(Status(StatusCode.ERROR, status))
    elif status == "succeeded":
        span.set_status(Status(StatusCode.OK))


def record_tool_result(span: Span, result: str) -> None:
    span.set_attribute("operion.result", result)
    span.set_attribute("langfuse.observation.metadata.result", result)
    technical_error = result in {
        "source_unavailable",
        "read_tool_error",
        "internal_error",
    }
    span.set_attribute(
        "langfuse.observation.level",
        "ERROR"
        if technical_error
        else ("DEFAULT" if result == "success" else "WARNING"),
    )
    span.set_attribute("langfuse.observation.status_message", result)
    if technical_error:
        span.set_status(Status(StatusCode.ERROR, result))
    elif result == "success":
        span.set_status(Status(StatusCode.OK))


_run_labels: ContextVar[tuple[str, str] | None] = ContextVar(
    "operion_run_labels", default=None
)
_experiment_labels: ContextVar[dict[str, str] | None] = ContextVar(
    "operion_experiment_labels", default=None
)


@contextmanager
def agent_run_labels(conversation_id: str, run_id: str) -> Iterator[None]:
    """Propagate validated identifiers to local child spans without HTTP baggage."""
    token = _run_labels.set((conversation_id, run_id))
    try:
        yield
    finally:
        _run_labels.reset(token)


@contextmanager
def experiment_labels(labels: dict[str, str]) -> Iterator[None]:
    token = _experiment_labels.set(labels)
    try:
        yield
    finally:
        _experiment_labels.reset(token)


def run_span_ids(span: Span) -> tuple[str | None, str | None]:
    context = span.get_span_context()
    if not context.is_valid:
        return None, None
    return f"{context.trace_id:032x}", f"{context.span_id:016x}"


def current_span_ids() -> tuple[str | None, str | None]:
    return run_span_ids(trace.get_current_span())


def action_trace_links(action: dict) -> list:
    """Link a worker span to the persisted approval, or to its proposal."""
    from opentelemetry.trace import Link, SpanContext, TraceFlags

    for prefix in ("approval", "proposal"):
        trace_id = action.get(f"{prefix}_trace_id")
        span_id = action.get(f"{prefix}_span_id")
        if not isinstance(trace_id, str) or not isinstance(span_id, str):
            continue
        try:
            context = SpanContext(
                trace_id=int(trace_id, 16),
                span_id=int(span_id, 16),
                is_remote=True,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
        except ValueError:
            continue
        if len(trace_id) == 32 and len(span_id) == 16 and context.is_valid:
            return [Link(context)]
    return []


def configure_observability(service_name: str, *, agent: bool = False):
    """Install one provider when explicitly enabled; return it for shutdown.

    The optional observability extra is required only when tracing is enabled.
    Export always targets an OTLP/HTTP collector, never a Langfuse UI URL.
    """
    if os.environ.get("OPERION_OTEL_ENABLED") != "1":
        return None

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    class RunLabelsProcessor(SpanProcessor):
        def on_start(self, span, parent_context=None) -> None:
            span.set_attribute("langfuse.environment", environment)
            span.set_attribute("langfuse.release", release)
            span.set_attribute("langfuse.version", release)
            span.set_attribute(
                "operion.telemetry.content_enabled", content_capture_enabled()
            )
            labels = _run_labels.get()
            if labels is not None:
                span.set_attribute("langfuse.session.id", labels[0])
                span.set_attribute("langfuse.trace.metadata.run_id", labels[1])
            experiment = _experiment_labels.get()
            if experiment is not None:
                for key, value in experiment.items():
                    span.set_attribute(key, value)

        def on_end(self, span) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces"
    )
    release = os.environ.get("OPERION_RELEASE_ID", "dev")
    environment = os.environ.get(
        "OPERION_TELEMETRY_ENVIRONMENT", os.environ.get("OPERION_ENVIRONMENT", "local")
    )
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": release,
            "deployment.environment.name": environment,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(RunLabelsProcessor())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    if agent:
        from pydantic_ai import Agent
        from pydantic_ai.models.instrumented import InstrumentationSettings

        Agent.instrument_all(
            InstrumentationSettings(
                tracer_provider=provider,
                include_content=content_capture_enabled(),
                include_binary_content=False,
                include_model_request_parameters=content_capture_enabled(),
            )
        )
    return provider


def instrument_fastapi(app, provider) -> None:
    if provider is None:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/health",
        exclude_spans=["receive", "send"],
    )
