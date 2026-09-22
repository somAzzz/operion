from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic_ai import Agent

from .agent_runtime import AgentDependencies, AgentSettings, create_operion_agent
from .read_tools import AccessScope, CanonicalRepository, SourceUnavailableError


class UnavailableRepository:
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


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_walk_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_walk_keys(item) for item in value))
    return set()


def grade_case(
    case: dict[str, Any], calls: list[dict[str, Any]], answer: str
) -> list[str]:
    failures: list[str] = []
    expected_tool = case.get("tool")
    matching = (
        [call for call in calls if call["name"] == expected_tool]
        if expected_tool
        else calls
    )
    if case.get("expected_tool_call", "not-set") is None:
        if calls:
            failures.append("unexpected_tool_call")
        return failures
    tool_is_optional = bool(case.get("tool_optional", False))
    if expected_tool and not matching and not tool_is_optional:
        return ["expected_tool_not_called"]

    payload = matching[-1]["result"] if matching else {}
    if expected_error := case.get("expected_error"):
        if payload.get("error", {}).get("code") != expected_error:
            failures.append("wrong_error")
    if expected := case.get("expected"):
        data = payload.get("data", {})
        customer = data.get("customer", {})
        if customer.get("canonical_id") != expected.get("customer_id"):
            failures.append("wrong_customer")
        if len(data.get("orders", [])) != expected.get("order_count"):
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
    forbidden_claim = case.get("forbidden_claim")
    if forbidden_claim and forbidden_claim in answer:
        claim_index = answer.index(forbidden_claim)
        preceding = answer[max(0, claim_index - 8) : claim_index]
        if "不是" not in preceding and "并非" not in preceding:
            failures.append("forbidden_claim")
    if not answer.strip():
        failures.append("empty_answer")
    return failures


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
    definition = json.loads(inputs.cases.read_text(encoding="utf-8"))
    scope_definition = definition["default_scope"]
    scope = AccessScope(
        scope_definition["operating_company"],
        frozenset(scope_definition["customer_ids"]),
    )
    agent: Agent[AgentDependencies, str] = create_operion_agent(settings)
    runs: list[dict[str, Any]] = []
    started_at = datetime.now(UTC)
    for repeat in range(1, definition["repeat_count"] + 1):
        for case in definition["cases"]:
            deps = AgentDependencies(
                repository=_repository(inputs, case),
                scope=scope,
                user_id="e2-evaluator",
            )
            started = monotonic()
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
            except Exception as exception:  # evaluator must preserve failed evidence
                error = f"{type(exception).__name__}: {exception}"
                usage = {}
            failures = grade_case(case, deps.tool_calls, answer)
            if error:
                failures.append("agent_run_error")
            runs.append(
                {
                    "case_id": case["id"],
                    "repeat": repeat,
                    "passed": not failures,
                    "failures": failures,
                    "duration_seconds": round(monotonic() - started, 3),
                    "answer": answer,
                    "tool_calls": deps.tool_calls,
                    "usage": usage,
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
    report = {
        "report_version": "operion-e2-agent-evaluation-v1",
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
    }
    inputs.output.parent.mkdir(parents=True, exist_ok=True)
    inputs.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
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
    args = parser.parse_args()
    report = asyncio.run(
        evaluate(
            EvaluationInputs(
                cases=args.cases,
                canonical_directory=args.canonical_directory,
                identity_map=args.identity_map,
                output=args.output,
                observed_at=args.observed_at,
            ),
            AgentSettings.from_environment(),
        )
    )
    print(
        json.dumps({key: report[key] for key in ("status", "run_count", "passed_runs")})
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
