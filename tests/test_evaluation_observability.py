import asyncio
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from operion_etl.agent_runtime import AgentSettings
from operion_etl.answer_evidence import AnswerPlan
from operion_etl.e2_evaluation import EvaluationInputs, evaluate
from operion_etl.evaluation_observability import publish_langfuse_scores


class EvaluationObservabilityTests(unittest.TestCase):
    def test_synthetic_evaluation_creates_one_scored_trace_per_item(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("operion.evaluation")

        class FakeAgent:
            async def run(self, question, **kwargs):
                deps = kwargs["deps"]
                deps.answer_plan = AnswerPlan(language="en", notice="needs_details")
                return SimpleNamespace(
                    output=deps.evidence.render(deps.answer_plan),
                    usage=SimpleNamespace(
                        input_tokens=2, output_tokens=3, requests=1, tool_calls=0
                    ),
                )

        try:
            with tempfile.TemporaryDirectory() as directory:
                case_path = Path(directory) / "cases.json"
                case_path.write_text(
                    json.dumps(
                        {
                            "version": "synthetic-v1",
                            "repeat_count": 1,
                            "default_scope": {
                                "operating_company": "Synthetic Co",
                                "customer_ids": [],
                            },
                            "cases": [
                                {
                                    "id": "S01",
                                    "question": "synthetic input",
                                    "expected_tool_call": None,
                                }
                            ],
                        }
                    )
                )
                inputs = EvaluationInputs(
                    cases=case_path,
                    canonical_directory=Path(directory),
                    identity_map=Path(directory) / "unused.csv",
                    output=Path(directory) / "report.json",
                    observed_at="2026-10-01T00:00:00Z",
                    langfuse_experiment=True,
                    synthetic_data_confirmed=True,
                )
                with (
                    patch.dict(os.environ, {"OPERION_OTEL_ENABLED": "1"}),
                    patch(
                        "operion_etl.e2_evaluation.create_operion_agent",
                        return_value=FakeAgent(),
                    ),
                    patch(
                        "operion_etl.e2_evaluation._repository", return_value=object()
                    ),
                    patch(
                        "operion_etl.e2_evaluation.publish_langfuse_scores"
                    ) as publish,
                    patch(
                        "operion_etl.evaluation_observability.trace.get_tracer",
                        return_value=tracer,
                    ),
                ):
                    report = asyncio.run(evaluate(inputs, AgentSettings()))
                self.assertEqual("passed", report["status"])
                self.assertEqual("submitted", report["langfuse_score_export"])
                score = publish.call_args.args[0][0]
                span = exporter.get_finished_spans()[0]
                self.assertEqual(f"{span.context.trace_id:032x}", score["trace_id"])
                self.assertEqual(f"{span.context.span_id:016x}", score["span_id"])
                self.assertEqual(
                    "synthetic input",
                    json.loads(span.attributes["langfuse.observation.input"]),
                )
                self.assertEqual(
                    "synthetic-v1", span.attributes["langfuse.experiment.dataset.id"]
                )
        finally:
            provider.shutdown()

    def test_content_export_requires_explicit_synthetic_confirmation(self):
        inputs = EvaluationInputs(
            cases=Path("unused"),
            canonical_directory=Path("unused"),
            identity_map=Path("unused"),
            output=Path("unused"),
            observed_at="2026-10-01T00:00:00Z",
            langfuse_experiment=True,
        )
        with self.assertRaisesRegex(ValueError, "confirmed synthetic data"):
            asyncio.run(evaluate(inputs, AgentSettings()))

    def test_score_api_uses_the_observation_and_boolean_result(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(
                    (
                        self.path,
                        self.headers.get("Authorization"),
                        json.loads(
                            self.rfile.read(int(self.headers["Content-Length"]))
                        ),
                    )
                )
                self.send_response(201)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(
                os.environ,
                {
                    "LANGFUSE_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    "LANGFUSE_PUBLIC_KEY": "pk-test",
                    "LANGFUSE_SECRET_KEY": "sk-test",
                },
            ):
                publish_langfuse_scores(
                    [
                        {
                            "experiment_id": "exp-1",
                            "case_id": "S01",
                            "repeat": 1,
                            "trace_id": "a" * 32,
                            "span_id": "b" * 16,
                            "passed": False,
                            "failures": ["wrong_order_count"],
                            "score_name": "operion_guardrail_acceptance",
                        }
                    ]
                )
            self.assertEqual("/api/public/scores", received[0][0])
            self.assertTrue(received[0][1].startswith("Basic "))
            self.assertEqual("b" * 16, received[0][2]["observationId"])
            self.assertEqual(0, received[0][2]["value"])
            self.assertIs(type(received[0][2]["value"]), int)
            self.assertEqual("wrong_order_count", received[0][2]["comment"])
            self.assertEqual("operion_guardrail_acceptance", received[0][2]["name"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
