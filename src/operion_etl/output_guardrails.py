"""Evidence-based gate for explicit business facts in Agent answers.

This is deliberately narrower than natural-language truth checking. It blocks
claims whose count, amount, object, status, or fulfillment result contradicts
the server-side tool evidence available to this run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from opentelemetry import trace

from .answer_claims import (
    AMOUNT_PATTERN,
    CANONICAL_ID_PATTERN,
    asserted_fulfillment_results,
    asserted_order_count_claims,
    asserted_statuses,
)


class GuardrailVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GuardrailDecision:
    name: str
    verdict: GuardrailVerdict
    reason_code: str


def record_guardrail(decision: GuardrailDecision) -> None:
    """Export only stable policy labels, never prompts or business records."""
    with trace.get_tracer("operion.guardrails").start_as_current_span(
        f"operion.guardrail.{decision.name}",
        attributes={
            "langfuse.observation.type": "guardrail",
            "langfuse.observation.metadata.guardrail": decision.name,
            "langfuse.observation.metadata.verdict": decision.verdict.value,
            "langfuse.observation.metadata.reason_code": decision.reason_code,
            "langfuse.observation.level": (
                "DEFAULT" if decision.verdict is GuardrailVerdict.ALLOW else "WARNING"
            ),
            "langfuse.observation.status_message": decision.reason_code,
            "operion.guardrail.policy_version": "business-facts-v2",
        },
    ):
        pass


def verify_business_answer(
    tool_calls: list[dict[str, Any]], answer: str
) -> GuardrailDecision:
    """Check explicit claims against all successful, server-recorded tool results.

    UNKNOWN means the answer asserts a protected fact without sufficient tool
    evidence. Both UNKNOWN and DENY must be withheld from the user-facing stream.
    """
    allow = GuardrailDecision("output_facts", GuardrailVerdict.ALLOW, "FACTS_SUPPORTED")
    if not answer.strip():
        return GuardrailDecision(
            "output_facts", GuardrailVerdict.UNKNOWN, "EMPTY_ANSWER"
        )
    successful = [
        call
        for call in tool_calls
        if isinstance(call.get("result"), dict)
        and call["result"].get("ok") is True
        and isinstance(call["result"].get("data"), dict)
    ]
    data_items = [call["result"]["data"] for call in successful]
    from .business_facts import bound_fact_errors

    claimed_ids = set(CANONICAL_ID_PATTERN.findall(answer))
    evidence_ids = set().union(
        *(
            set(CANONICAL_ID_PATTERN.findall(json.dumps(data, ensure_ascii=False)))
            for data in data_items
        )
    )
    if claimed_ids - evidence_ids:
        return GuardrailDecision(
            "output_facts", GuardrailVerdict.UNKNOWN, "OBJECT_ID_UNVERIFIED"
        )

    errors = bound_fact_errors(successful, answer)
    if errors:
        return GuardrailDecision(
            "output_facts",
            GuardrailVerdict.DENY
            if errors[0].endswith("MISMATCH")
            else GuardrailVerdict.UNKNOWN,
            errors[0],
        )

    claimed_results = asserted_fulfillment_results(answer)
    if claimed_results - {"insufficient_information"}:
        evidence_results = {
            call["result"]["data"].get("result")
            for call in successful
            if call.get("name") == "check_fulfillment"
        }
        if not (claimed_results - {"insufficient_information"}) <= evidence_results:
            return GuardrailDecision(
                "output_facts", GuardrailVerdict.UNKNOWN, "FULFILLMENT_UNVERIFIED"
            )
        if "satisfiable" in claimed_results and any(
            call["result"]["data"].get("data_mode") == "live"
            for call in successful
            if call.get("name") == "check_fulfillment"
        ):
            return GuardrailDecision(
                "output_facts", GuardrailVerdict.DENY, "LIVE_FULFILLMENT_UNSUPPORTED"
            )

    if re.search(
        r"(?:全部|所有|完整|all)\s*(?:的)?\s*(?:历史|historical)\s*(?:销售|采购)?订单",
        answer,
        re.I,
    ):
        if any(
            isinstance(data.get("completeness"), dict)
            and data["completeness"].get("full_source_history") == "undetermined"
            for data in data_items
        ):
            return GuardrailDecision(
                "output_facts", GuardrailVerdict.UNKNOWN, "HISTORY_SCOPE_UNVERIFIED"
            )
    if not (
        claimed_ids
        or claimed_results
        or asserted_order_count_claims(answer)
        or AMOUNT_PATTERN.search(answer)
        or asserted_statuses(answer)
    ):
        return GuardrailDecision(
            "output_facts", GuardrailVerdict.ALLOW, "NO_PROTECTED_CLAIMS"
        )
    return allow
