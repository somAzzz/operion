"""Validate a closed structured plan against server-owned current-run evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from opentelemetry import trace

from .answer_evidence import AnswerPlan, EvidenceError, EvidenceRegistry


class GuardrailVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GuardrailDecision:
    name: str
    verdict: GuardrailVerdict
    reason_code: str
    reference: str = ""
    fact_count: int = 0
    table_count: int = 0


def verify_answer_plan(
    registry: EvidenceRegistry, plan: AnswerPlan
) -> GuardrailDecision:
    try:
        registry.validate(plan)
    except EvidenceError as exc:
        return GuardrailDecision(
            "output_facts",
            GuardrailVerdict.DENY,
            exc.code,
            exc.reference
            if exc.reference in registry.facts or exc.reference in registry.tables
            else "",
        )
    return GuardrailDecision(
        "output_facts",
        GuardrailVerdict.ALLOW,
        "STRUCTURED_EVIDENCE_SUPPORTED",
        fact_count=len(plan.facts),
        table_count=len(plan.tables),
    )


def record_guardrail(decision: GuardrailDecision) -> None:
    """Export diagnostics without copying business values or model prose."""
    with trace.get_tracer("operion.guardrails").start_as_current_span(
        f"operion.guardrail.{decision.name}",
        attributes={
            "langfuse.observation.type": "guardrail",
            "langfuse.observation.metadata.guardrail": decision.name,
            "langfuse.observation.metadata.verdict": decision.verdict.value,
            "langfuse.observation.metadata.reason_code": decision.reason_code,
            "langfuse.observation.metadata.reference": decision.reference,
            "langfuse.observation.metadata.fact_count": decision.fact_count,
            "langfuse.observation.metadata.table_count": decision.table_count,
            "langfuse.observation.level": "DEFAULT"
            if decision.verdict is GuardrailVerdict.ALLOW
            else "WARNING",
            "langfuse.observation.status_message": decision.reason_code,
            "operion.guardrail.policy_version": "structured-evidence-v1",
        },
    ):
        pass
