"""Evidence-based gate for explicit business facts in Agent answers.

This is deliberately narrower than natural-language truth checking. It blocks
claims whose count, amount, object, status, or fulfillment result contradicts
the server-side tool evidence available to this run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
            "operion.guardrail.policy_version": "business-facts-v1",
        },
    ):
        pass


def _numbers(data: dict[str, Any]) -> set[int]:
    numbers: set[int] = set()
    for key in ("order_count", "sales_order_count"):
        value = data.get(key)
        if type(value) is int and value >= 0:
            numbers.add(value)
    completeness = data.get("completeness")
    if isinstance(completeness, dict):
        total = completeness.get("total_count")
        # A paged list can be partial while its filtered total is still exact.
        if type(total) is int and total >= 0:
            numbers.add(total)
    if not numbers and isinstance(data.get("orders"), list):
        # An overview without a separate count contains the current result set.
        # Never confuse a paginated list's page length with its total count.
        if (
            not isinstance(completeness, dict)
            or completeness.get("status") == "complete"
        ):
            numbers.add(len(data["orders"]))
    return numbers


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


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
    counts = set().union(*(_numbers(data) for data in data_items))
    named_counts = [
        (
            row.get("customer_name") or row.get("name") or row.get("customer_id"),
            row.get("order_count"),
        )
        for data in data_items
        for key in ("customer_order_counts", "customers")
        for row in (data.get(key) if isinstance(data.get(key), list) else [])
        if isinstance(row, dict) and type(row.get("order_count")) is int
    ]
    for claimed, context in asserted_order_count_claims(answer):
        mentioned_counts = [
            count
            for name, count in named_counts
            if isinstance(name, str) and name.casefold() in context.casefold()
        ]
        if (
            claimed not in mentioned_counts
            if mentioned_counts
            else claimed not in counts
        ):
            return GuardrailDecision(
                "output_facts",
                GuardrailVerdict.DENY
                if counts or named_counts
                else GuardrailVerdict.UNKNOWN,
                "ORDER_COUNT_MISMATCH"
                if counts or named_counts
                else "ORDER_COUNT_UNVERIFIED",
            )

    if not any(call.get("name") == "check_operation_capability" for call in successful):
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

    claimed_amounts = {
        match.group(1) or match.group(2) or match.group(3)
        for match in AMOUNT_PATTERN.finditer(answer)
    }
    if claimed_amounts:
        amounts: set[Decimal] = set()
        for data in data_items:
            for row in _walk(data):
                for key in ("net_total_ex_tax", "net_amount", "unit_price_ex_tax"):
                    if key in row:
                        try:
                            amounts.add(Decimal(str(row[key]).replace(",", "")))
                        except InvalidOperation:
                            pass
        if any(
            Decimal(value.replace(",", "")) not in amounts for value in claimed_amounts
        ):
            return GuardrailDecision(
                "output_facts", GuardrailVerdict.UNKNOWN, "AMOUNT_UNVERIFIED"
            )

    claimed_statuses = asserted_statuses(answer)
    if claimed_statuses:
        statuses = {
            str(row[key]).casefold().replace(" ", "_")
            for data in data_items
            for row in _walk(data)
            for key in ("business_status", "source_status")
            if row.get(key)
        }
        if claimed_statuses - statuses:
            return GuardrailDecision(
                "output_facts", GuardrailVerdict.UNKNOWN, "STATUS_UNVERIFIED"
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
    return allow
