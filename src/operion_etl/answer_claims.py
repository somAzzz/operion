"""Conservative, deterministic extraction of explicit business claims.

The same extractors are used by offline evaluation and the runtime output gate.
They deliberately do not try to infer unstated facts from natural language.
"""

from __future__ import annotations

import re

COUNT_PATTERN = re.compile(
    r"([零〇一二两三四五六七八九十百千\d,]+)\*{0,2}\s*(?:张|笔|个|条)?\s*(?:销售|采购)?订单"
    r"|\b(\d[\d,]*)\*{0,2}\s+(?:sales? |purchase )?orders?\b",
    re.IGNORECASE,
)
ORDER_COUNT_PREFIX_PATTERN = re.compile(
    r"(?:销售|采购)?订单(?:总数|数量|数|量)?\s*"
    r"(?:[（(]\s*共\s*|[:：=]\s*|为\s*|是\s*)"
    r"\*{0,2}([零〇一二两三四五六七八九十百千\d,]+)\*{0,2}\s*(?:张|笔|个|条)?"
)
CANONICAL_ID_PATTERN = re.compile(r"\b(?:operion|wwi):[A-Za-z0-9_:.-]+")
AMOUNT_PATTERN = re.compile(
    r"(?:EUR|USD|€|\$)\s*([\d,]+(?:\.\d+)?)"
    r"|([\d,]+(?:\.\d+)?)\s*(?:EUR|USD|欧元|美元)"
    r"|(?:net amount(?: excluding tax)?|net total|order total|金额|净额|总额)"
    r"\*{0,2}\s*[:：]?\s*\*{0,2}\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
STATUS_PATTERN = re.compile(
    r"(?:状态|status)\*{0,2}\s*(?:为|是|:|：|=)?\s*\*{0,2}\s*"
    r"(to_deliver|to_receive|completed|cancelled|draft|closed|picked|open|invoiced|待交付|待收货|已完成|已取消|草稿|已拣货)",
    re.IGNORECASE,
)
STATUS_ALIASES = {
    "待交付": "to_deliver",
    "待收货": "to_receive",
    "已完成": "completed",
    "已取消": "cancelled",
    "草稿": "draft",
    "已拣货": "picked",
}
RESULT_TERMS = {
    "shortfall": r"库存不足|短缺|无法满足|\b(?:shortfall|stock shortage)\b",
    "insufficient_information": (
        r"信息不足|证据不足|无法判断|无法确认|"
        r"\binsufficient(?:_information| information)\b|cannot determine"
    ),
    "satisfiable": (
        r"可以履约|可满足|可交付|库存充足|\b(?:satisfiable|sufficient|can fulfill)\b"
    ),
}


def _integer(value: str) -> int:
    value = value.replace(",", "")
    if value.isdecimal():
        return int(value)
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    total = current = 0
    for character in value:
        if character in digits:
            current = digits[character]
        elif character in units:
            total += (current or 1) * units[character]
            current = 0
    return total + current


def _claim_context(answer: str, start: int, end: int) -> str:
    left = max(
        answer.rfind(separator, 0, start) for separator in ("。", ";", "；", "\n")
    )
    right_edges = [
        edge
        for separator in ("。", ";", "；", "\n")
        if (edge := answer.find(separator, end)) >= 0
    ]
    right = min(right_edges, default=len(answer))
    return answer[left + 1 : right]


def asserted_order_count_claims(answer: str) -> list[tuple[int, str]]:
    claims = []
    for match in COUNT_PATTERN.finditer(answer):
        preceding = answer[max(0, match.start() - 4) : match.start()]
        if any(
            word in preceding for word in ("不是", "并非", "不等于", "至少", "多于")
        ):
            continue
        claims.append(
            (
                _integer(match.group(1) or match.group(2)),
                _claim_context(answer, match.start(), match.end()),
            )
        )
    for match in ORDER_COUNT_PREFIX_PATTERN.finditer(answer):
        claims.append(
            (
                _integer(match.group(1)),
                _claim_context(answer, match.start(), match.end()),
            )
        )
    for match in re.finditer(
        r"(?:没有|无|零)\s*(?:任何)?\s*(?:销售|采购)?订单(?!被(?:删除|修改|创建|更新))"
        r"|\bno orders?\b(?!\s+(?:was|were|has been|have been)\s+(?:deleted|changed|created|updated))",
        answer,
        re.I,
    ):
        claims.append((0, _claim_context(answer, match.start(), match.end())))
    return claims


def asserted_order_counts(answer: str) -> list[int]:
    return [count for count, _ in asserted_order_count_claims(answer)]


def asserted_statuses(answer: str) -> set[str]:
    return {
        STATUS_ALIASES.get(match.group(1), match.group(1)).casefold()
        for match in STATUS_PATTERN.finditer(answer)
    }


def asserted_fulfillment_results(answer: str) -> set[str]:
    normalized = answer.casefold()
    claims: set[str] = set()
    for status, pattern in RESULT_TERMS.items():
        for match in re.finditer(pattern, normalized):
            preceding = normalized[max(0, match.start() - 16) : match.start()]
            if re.search(
                r"(?:未给出|而非明确的|而非|并非|不是|不能|不代表|未能|没有|无|不|no|not)\W*$",
                preceding,
            ):
                continue
            claims.add(status)
    return claims
