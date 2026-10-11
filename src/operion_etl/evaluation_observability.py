"""Opt-in Langfuse experiment records for explicitly synthetic evaluations."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context

from .observability import experiment_labels, run_span_ids


@contextmanager
def synthetic_case_span(
    experiment_id: str,
    dataset_id: str,
    case_id: str,
    repeat: int,
    question: str,
    expected: dict[str, Any],
) -> Iterator[Any]:
    item_id = f"{case_id}-{repeat}"
    labels = {
        "langfuse.experiment.id": experiment_id,
        "langfuse.experiment.name": "operion-e2-deterministic",
        "langfuse.experiment.dataset.id": dataset_id,
        "langfuse.experiment.item.id": item_id,
        "langfuse.environment": "experiment",
    }
    with trace.get_tracer("operion.evaluation").start_as_current_span(
        "operion.evaluation.case",
        context=Context(),
        attributes={
            **labels,
            "langfuse.observation.type": "evaluator",
            "langfuse.observation.input": json.dumps(question, ensure_ascii=False),
            "langfuse.experiment.item.expected_output": json.dumps(
                expected, ensure_ascii=False, sort_keys=True
            ),
        },
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        _, span_id = run_span_ids(span)
        if span_id:
            span.set_attribute("langfuse.experiment.item.root_observation_id", span_id)
        with experiment_labels(
            labels
            | {
                "langfuse.experiment.item.root_observation_id": span_id or "",
            }
        ):
            yield span


def publish_langfuse_scores(records: list[dict[str, Any]]) -> None:
    """Publish deterministic scores through Langfuse's supported Scores API."""
    base_url = os.environ.get("LANGFUSE_BASE_URL", "").rstrip("/")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not all((base_url, public_key, secret_key)):
        raise RuntimeError("Langfuse score export requires base URL and project keys")
    credentials = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode(
        "ascii"
    )
    for record in records:
        payload = {
            "id": f"{record['experiment_id']}-{record['case_id']}-{record['repeat']}",
            "traceId": record["trace_id"],
            "observationId": record["span_id"],
            "name": record.get("score_name", "operion_correctness"),
            "value": int(record["passed"]),
            "dataType": "BOOLEAN",
            "comment": ",".join(record["failures"]) or "deterministic checks passed",
        }
        request = urllib.request.Request(
            f"{base_url}/api/public/scores",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError("Langfuse score export was rejected")
        except (urllib.error.HTTPError, urllib.error.URLError) as error:
            raise RuntimeError(
                f"Langfuse score export failed: {type(error).__name__}"
            ) from None
