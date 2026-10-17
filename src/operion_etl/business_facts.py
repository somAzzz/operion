"""Entity- and field-bound evidence for the supported explicit answer grammar.

Ambiguous references fail closed. This is not a general natural-language parser.
Evidence stays local; callers export reason codes rather than business values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .answer_claims import (
    AMOUNT_PATTERN,
    CANONICAL_ID_PATTERN,
    STATUS_ALIASES,
    STATUS_PATTERN,
    _claim_context,
    asserted_customer_counts,
    asserted_order_count_claims,
)


@dataclass(frozen=True)
class Fact:
    entity: str
    aliases: tuple[str, ...]
    field: str
    value: str
    currency: str
    evidence_pointer: str


def evidence_facts(calls: list[dict[str, Any]]) -> list[Fact]:
    facts: list[Fact] = []

    def add(row, field, value, pointer, fallback=""):
        entity = str(
            row.get("canonical_id")
            or row.get("customer_id")
            or row.get("supplier_id")
            or fallback
        )
        aliases = tuple(
            str(row[k])
            for k in (
                "canonical_id",
                "customer_id",
                "supplier_id",
                "name",
                "customer_name",
                "supplier_name",
                "order_number",
            )
            if row.get(k)
        )
        facts.append(
            Fact(
                entity,
                aliases,
                field,
                str(value),
                str(row.get("currency", "")).upper(),
                pointer,
            )
        )

    def walk(value, pointer):
        if isinstance(value, dict):
            # An order's customer name identifies its owner, not the order itself.
            if value.get("canonical_id"):
                row = dict(value)
                if "net_total_ex_tax" in row:
                    for key in (
                        "customer_id",
                        "customer_name",
                        "supplier_id",
                        "supplier_name",
                    ):
                        row.pop(key, None)
                for field in (
                    "net_total_ex_tax",
                    "net_amount",
                    "unit_price_ex_tax",
                    "business_status",
                    "source_status",
                ):
                    if value.get(field) not in (None, ""):
                        add(row, field, value[field], pointer + "/" + field)
            for key, child in value.items():
                walk(child, pointer + "/" + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, pointer + "/" + str(index))

    for index, call in enumerate(calls):
        result = call.get("result", {})
        if not isinstance(result, dict) or result.get("ok") is not True:
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        pointer = f"/calls/{index}/result/data"
        walk(data, pointer)
        owner = data.get("customer") or data.get("supplier") or {}
        if not isinstance(owner, dict):
            owner = {}
        count = data.get("order_count", data.get("sales_order_count"))
        completeness = data.get("completeness", data.get("order_completeness", {}))
        if count is None and isinstance(completeness, dict):
            count = completeness.get("total_count")
        if count is None and isinstance(data.get("orders"), list):
            if not completeness or completeness.get("status") == "complete":
                count = len(data["orders"])
        if type(count) is int:
            add(owner, "order_count", count, pointer, f"query:{index}")
        for key in ("customers", "customer_order_counts"):
            for row in data.get(key, []) if isinstance(data.get(key), list) else []:
                if isinstance(row, dict) and type(row.get("order_count")) is int:
                    add(row, "order_count", row["order_count"], pointer + "/" + key)
    return facts


def _matches(alias: str, text: str) -> bool:
    return bool(
        re.search(r"(?<![\w:.-])" + re.escape(alias) + r"(?![\w:.-])", text, re.I)
    )


def _select(facts: list[Fact], context: str, field: str) -> list[Fact]:
    candidates = [fact for fact in facts if fact.field == field]
    mentioned = {
        fact.entity
        for fact in candidates
        if any(_matches(alias, context) for alias in fact.aliases)
    }
    claimed_ids = set(CANONICAL_ID_PATTERN.findall(context))
    if mentioned:
        return (
            [fact for fact in candidates if fact.entity in mentioned]
            if len(mentioned) == 1
            else []
        )
    if claimed_ids:
        return []
    # Never borrow a value from another object when the subject is unresolved.
    return candidates if len({fact.entity for fact in candidates}) == 1 else []


def bound_fact_errors(calls: list[dict[str, Any]], answer: str) -> list[str]:
    facts = evidence_facts(calls)
    errors: list[str] = []
    customer_counts = set()
    for call in calls:
        result = call.get("result", {})
        if not isinstance(result, dict) or result.get("ok") is not True:
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        if type(data.get("customer_count")) is int:
            customer_counts.add(data["customer_count"])
        elif (
            call.get("name") == "search_customers"
            and not data.get("query")
            and data.get("completeness", {}).get("status") == "complete"
            and isinstance(data.get("results"), list)
        ):
            customer_counts.add(len(data["results"]))
    for count in asserted_customer_counts(answer):
        if count not in customer_counts:
            errors.append(
                "CUSTOMER_COUNT_MISMATCH"
                if customer_counts
                else "CUSTOMER_COUNT_UNVERIFIED"
            )
    for count, context in asserted_order_count_claims(answer):
        selected = _select(facts, context, "order_count")
        if not selected or any(fact.value != str(count) for fact in selected):
            errors.append(
                "ORDER_COUNT_MISMATCH"
                if any(f.field == "order_count" for f in facts)
                else "ORDER_COUNT_UNVERIFIED"
            )
    for match in AMOUNT_PATTERN.finditer(answer):
        context = _claim_context(answer, match.start(), match.end())
        labels = list(
            re.finditer(
                r"unit price|单价|line (?:amount|total)|行金额|明细金额|net amount|net total|order total|金额|净额|总额",
                answer[max(0, match.start() - 80) : match.end()],
                re.I,
            )
        )
        label = labels[-1].group().casefold() if labels else ""
        field = (
            "unit_price_ex_tax"
            if label in ("unit price", "单价")
            else "net_amount"
            if label in ("line amount", "line total", "行金额", "明细金额")
            else "net_total_ex_tax"
        )
        selected = _select(facts, context, field)
        currency_match = re.search(r"EUR|USD|€|\$|欧元|美元", match.group(), re.I)
        if currency_match is None:
            currency_match = re.match(
                r"\s*(EUR|USD|€|\$|欧元|美元)", answer[match.end() :], re.I
            )
        currency = currency_match.group().strip().upper() if currency_match else ""
        currency = {"€": "EUR", "欧元": "EUR", "$": "USD", "美元": "USD"}.get(
            currency, currency
        )
        value = Decimal(next(g for g in match.groups() if g).replace(",", ""))
        try:
            valid = selected and all(
                Decimal(f.value.replace(",", "")) == value
                and (not currency or f.currency == currency)
                for f in selected
            )
        except InvalidOperation:
            valid = False
        if not valid:
            errors.append("AMOUNT_UNVERIFIED")
    for match in STATUS_PATTERN.finditer(answer):
        context = _claim_context(answer, match.start(), match.end())
        field = (
            "source_status"
            if re.search(r"source status|来源状态", context, re.I)
            else "business_status"
        )
        selected = _select(facts, context, field)
        value = STATUS_ALIASES.get(match.group(1), match.group(1)).casefold()
        if not selected or any(
            f.value.casefold().replace(" ", "_") != value for f in selected
        ):
            errors.append("STATUS_UNVERIFIED")
    return list(dict.fromkeys(errors))
