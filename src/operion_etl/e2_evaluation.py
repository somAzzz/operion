from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic_ai import Agent

from .agent_runtime import AgentDependencies, AgentSettings, create_operion_agent
from .answer_evidence import AnswerPlan, EvidenceRegistry
from .evaluation_observability import publish_langfuse_scores, synthetic_case_span
from .observability import configure_observability, run_span_ids
from .output_guardrails import GuardrailVerdict, verify_answer_plan
from .read_tools import AccessScope, CanonicalRepository, SourceUnavailableError


class UnavailableRepository:
    data_mode = "snapshot"

    def customer_overview(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise SourceUnavailableError("canonical source is unavailable")

    def fulfillment_case(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise SourceUnavailableError("canonical source is unavailable")


@dataclass(frozen=True)
class EvaluationInputs:
    cases: Path
    canonical_directory: Path
    identity_map: Path
    output: Path
    observed_at: str
    langfuse_experiment: bool = False
    synthetic_data_confirmed: bool = False


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_walk_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_walk_keys(item) for item in value))
    return set()


def grade_case(
    case: dict[str, Any],
    calls: list[dict[str, Any]],
    answer: str,
    *,
    registry: EvidenceRegistry | None = None,
    plan: AnswerPlan | None = None,
) -> list[str]:
    failures: list[str] = []
    forbidden_tools = tuple(case.get("forbidden_tools", []))
    if any(
        call["name"].casefold().startswith(prefix.casefold())
        for call in calls
        for prefix in forbidden_tools
    ):
        failures.append("forbidden_tool_called")
    if "allowed_tools" in case and any(
        call["name"] not in case["allowed_tools"] for call in calls
    ):
        failures.append("unexpected_tool_call")
    expected_tool = case.get("tool")
    matching = (
        [call for call in calls if call["name"] == expected_tool]
        if expected_tool
        else calls
    )
    if case.get("expected_tool_call", "not-set") is None:
        if calls:
            failures.append("unexpected_tool_call")
    tool_is_optional = bool(case.get("tool_optional", False))
    if expected_tool and not matching and not tool_is_optional:
        return ["expected_tool_not_called"]

    payload = matching[-1]["result"] if matching else {}
    if expected_arguments := case.get("expected_arguments"):
        actual_arguments = matching[-1].get("arguments", {}) if matching else {}
        if any(
            actual_arguments.get(key) != value
            for key, value in expected_arguments.items()
        ):
            failures.append("wrong_tool_arguments")
    if expected_error := case.get("expected_error"):
        if payload.get("error", {}).get("code") != expected_error:
            failures.append("wrong_error")
    if expected := case.get("expected"):
        data = payload.get("data", {})
        customer = data.get("customer", {})
        if customer.get("canonical_id") != expected.get("customer_id"):
            failures.append("wrong_customer")
        if data.get("order_count", len(data.get("orders", []))) != expected.get(
            "order_count"
        ):
            failures.append("wrong_order_count")
        if expected.get("has_twenty_id") and not customer.get("twenty_id"):
            failures.append("missing_twenty_id")
        if expected.get("has_erpnext_id") and not customer.get("erpnext_id"):
            failures.append("missing_erpnext_id")
        if "missing" in expected and data.get("missing") != expected["missing"]:
            failures.append("wrong_missing_fields")
    if candidate_count := case.get("expected_candidate_count"):
        candidates = payload.get("error", {}).get("candidates", [])
        if len(candidates) != candidate_count:
            failures.append("wrong_candidate_count")
    if expected_result := case.get("expected_result"):
        if payload.get("data", {}).get("result") != expected_result:
            failures.append("wrong_result")
    if required_source := case.get("required_source"):
        if required_source not in payload.get("data", {}).get("sources", []):
            failures.append("missing_required_source")
    if required_missing := case.get("required_missing"):
        if required_missing not in payload.get("data", {}).get("missing", []):
            failures.append("missing_required_gap")
    forbidden_fields = set(case.get("forbidden_output_fields", []))
    if forbidden_fields & _walk_keys(payload):
        failures.append("forbidden_field_exposed")
    if registry is None or plan is None:
        failures.append("structured_answer_missing")
    else:
        decision = verify_answer_plan(registry, plan)
        if decision.verdict is not GuardrailVerdict.ALLOW:
            failures.append("answer_bound_" + decision.reason_code.lower())
        elif answer != registry.render(plan):
            failures.append("answer_render_mismatch")
        else:
            selected = [registry.facts[ref] for ref in plan.facts]
            if "order_count" in case.get("expected", {}):
                expected_count = case["expected"]["order_count"]
                if not any(
                    f.field in {"sales_order_count", "purchase_order_count"}
                    and f.value == expected_count
                    and (
                        not case["expected"].get("customer_id")
                        or f.entity == case["expected"]["customer_id"]
                    )
                    for f in selected
                ):
                    failures.append("answer_missing_order_count")
            if case.get("expected_result") and not any(
                f.field == "result" and f.value == case["expected_result"]
                for f in selected
            ):
                failures.append("answer_missing_result")
    if not answer.strip():
        failures.append("empty_answer")
    return list(dict.fromkeys(failures))


def _repository(inputs: EvaluationInputs, case: dict[str, Any]) -> Any:
    if case.get("fault") == "canonical_source_unavailable":
        return UnavailableRepository()
    observed_at = inputs.observed_at
    if case.get("fault") == "observed_at_older_than_stale_after_seconds":
        observed_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    return CanonicalRepository(
        inputs.canonical_directory,
        identity_map=inputs.identity_map,
        observed_at=observed_at,
        stale_after_seconds=3600,
    )


async def evaluate(inputs: EvaluationInputs, settings: AgentSettings) -> dict[str, Any]:
    if inputs.langfuse_experiment and not inputs.synthetic_data_confirmed:
        raise ValueError("Langfuse experiment export requires confirmed synthetic data")
    if inputs.langfuse_experiment and os.environ.get("OPERION_OTEL_ENABLED") != "1":
        raise ValueError("Langfuse experiment export requires OPERION_OTEL_ENABLED=1")
    definition = json.loads(inputs.cases.read_text(encoding="utf-8"))
    scope_definition = definition["default_scope"]
    scope = AccessScope(
        scope_definition["operating_company"],
        frozenset(scope_definition["customer_ids"]),
    )
    agent: Agent[AgentDependencies, str] = create_operion_agent(settings)
    runs: list[dict[str, Any]] = []
    score_records: list[dict[str, Any]] = []
    experiment_id = uuid4().hex if inputs.langfuse_experiment else None
    started_at = datetime.now(UTC)
    for repeat in range(1, definition["repeat_count"] + 1):
        for case in definition["cases"]:
            deps = AgentDependencies(
                repository=_repository(inputs, case),
                scope=scope,
                user_id="e2-evaluator",
            )
            expected = {
                key: value
                for key, value in case.items()
                if key.startswith("expected") or key == "required_source"
            }
            observation = (
                synthetic_case_span(
                    experiment_id,
                    definition["version"],
                    case["id"],
                    repeat,
                    case["question"],
                    expected,
                )
                if experiment_id is not None
                else nullcontext(None)
            )
            started = monotonic()
            with observation as eval_span:
                error: str | None = None
                answer = ""
                try:
                    result = await agent.run(
                        case["question"],
                        deps=deps,
                        usage_limits=settings.usage_limits(),
                    )
                    answer = result.output
                    usage = {
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                        "requests": result.usage.requests,
                        "tool_calls": result.usage.tool_calls,
                    }
                except Exception as exception:  # preserve local failed evidence
                    error = f"{type(exception).__name__}: {exception}"
                    usage = {}
                failures = grade_case(
                    case,
                    deps.tool_calls,
                    answer,
                    registry=deps.evidence,
                    plan=deps.answer_plan,
                )
                if error:
                    failures.append("agent_run_error")
                trace_id, span_id = (
                    run_span_ids(eval_span) if eval_span is not None else (None, None)
                )
                if eval_span is not None:
                    eval_span.set_attribute("operion.eval.passed", not failures)
                    eval_span.set_attribute(
                        "langfuse.observation.output",
                        json.dumps(
                            {"answer": answer, "failures": failures},
                            ensure_ascii=False,
                        ),
                    )
                    score_records.append(
                        {
                            "experiment_id": experiment_id,
                            "case_id": case["id"],
                            "repeat": repeat,
                            "trace_id": trace_id,
                            "span_id": span_id,
                            "passed": not failures,
                            "failures": failures,
                        }
                    )
                runs.append(
                    {
                        "case_id": case["id"],
                        "repeat": repeat,
                        "passed": not failures,
                        "failures": failures,
                        "duration_seconds": round(monotonic() - started, 3),
                        "answer": answer,
                        "answer_plan": deps.answer_plan.model_dump(mode="json")
                        if deps.answer_plan
                        else None,
                        "tool_calls": deps.tool_calls,
                        "usage": usage,
                        **(
                            {"trace_id": trace_id, "span_id": span_id}
                            if trace_id and span_id
                            else {}
                        ),
                        **({"error": error} if error else {}),
                    }
                )
    case_summary = {
        case["id"]: {
            "passed": all(
                run["passed"] for run in runs if run["case_id"] == case["id"]
            ),
            "runs": len([run for run in runs if run["case_id"] == case["id"]]),
        }
        for case in definition["cases"]
    }
    failure_categories = {
        "tool_selection": {"unexpected_tool_call", "expected_tool_not_called"},
        "parameters": {"wrong_tool_arguments"},
        "facts": {
            "wrong_customer",
            "wrong_order_count",
            "wrong_result",
            "answer_order_count_mismatch",
            "answer_result_mismatch",
            "unsupported_order_count_claim",
            "unsupported_amount_claim",
            "unsupported_object_claim",
            "unsupported_status_claim",
            "unsupported_result_claim",
            "answer_render_mismatch",
            "structured_answer_missing",
        },
        "evidence": {
            "missing_required_source",
            "missing_required_gap",
            "wrong_missing_fields",
            "missing_twenty_id",
            "missing_erpnext_id",
        },
        "permissions": {
            "wrong_error",
            "forbidden_field_exposed",
            "forbidden_claim",
            "wrong_candidate_count",
        },
        "task_completion": {
            "empty_answer",
            "agent_run_error",
            "answer_missing_order_count",
            "answer_missing_result",
        },
    }
    failure_categories["evidence"].update(
        failure
        for run in runs
        for failure in run["failures"]
        if failure.startswith("answer_bound_")
    )
    metrics = {
        category: {
            "passed_runs": sum(not (set(run["failures"]) & codes) for run in runs),
            "run_count": len(runs),
        }
        for category, codes in failure_categories.items()
    }
    report = {
        "report_version": "operion-e2-agent-evaluation-v3",
        "metrics": metrics,
        "status": "passed" if all(run["passed"] for run in runs) else "failed",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "model": settings.model_name,
        "model_base_url": settings.model_base_url,
        "thinking_enabled": settings.thinking_enabled,
        "case_count": len(definition["cases"]),
        "repeat_count": definition["repeat_count"],
        "run_count": len(runs),
        "passed_runs": sum(run["passed"] for run in runs),
        "cases": case_summary,
        "runs": runs,
        **({"langfuse_experiment_id": experiment_id} if experiment_id else {}),
    }
    inputs.output.parent.mkdir(parents=True, exist_ok=True)
    inputs.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if score_records:
        try:
            publish_langfuse_scores(score_records)
        except RuntimeError:
            report["langfuse_score_export"] = "failed"
            inputs.output.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n"
            )
            raise
        report["langfuse_score_export"] = "submitted"
        inputs.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-evaluate-e2")
    parser.add_argument("--cases", type=Path, default=Path("evaluations/e2/cases.json"))
    parser.add_argument(
        "--canonical-directory",
        type=Path,
        default=Path("data/canonical/operion-e2-demo-v1"),
    )
    parser.add_argument("--identity-map", type=Path, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--langfuse-experiment", action="store_true")
    parser.add_argument("--synthetic-data-confirmed", action="store_true")
    args = parser.parse_args()
    provider = configure_observability("operion-evaluation", agent=True)
    try:
        report = asyncio.run(
            evaluate(
                EvaluationInputs(
                    cases=args.cases,
                    canonical_directory=args.canonical_directory,
                    identity_map=args.identity_map,
                    output=args.output,
                    observed_at=args.observed_at,
                    langfuse_experiment=args.langfuse_experiment,
                    synthetic_data_confirmed=args.synthetic_data_confirmed,
                ),
                AgentSettings.from_environment(),
            )
        )
    finally:
        if provider is not None:
            provider.shutdown()
    print(
        json.dumps({key: report[key] for key in ("status", "run_count", "passed_runs")})
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
