#!/usr/bin/env python3
"""Run five read-only demo cases through Web, AG-UI, Agent, and tools."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    name: str
    prompt: str
    expected_tools: Counter[str]
    answer_markers: tuple[str, ...]


CASES = (
    Case(
        "customer_chain",
        "Find customers whose names contain Tailspin Toys. I choose "
        "wwi:organization:customer:65; show the customer, contacts, and all orders. "
        "Open sales order wwi:sales_order:66823 and explain ordered, picked, "
        "unpicked, and delivered quantities per line, including why picking "
        "does not prove delivery.",
        Counter(
            {
                "search_customers": 1,
                "get_customer_overview": 1,
                "get_sales_order": 1,
            }
        ),
        ("66823", "Picked", "Delivered", "unknown"),
    ),
    Case(
        "supplier_chain",
        "Find suppliers whose names contain Litware. I choose "
        "wwi:organization:supplier:7; show the supplier and all purchase orders. "
        "Open purchase order wwi:purchase_order:2044 and explain outer-pack "
        "quantity, base units per pack, base quantity, base-unit price, and "
        "line amount per line, then reconcile the total.",
        Counter(
            {
                "search_suppliers": 1,
                "get_supplier_overview": 1,
                "get_purchase_order": 1,
            }
        ),
        ("2044", "Base quantity", "75,620.00", "723,322.40"),
    ),
    Case(
        "two_order_compare",
        "Show customer wwi:organization:customer:65 and all its orders, then "
        "open sales orders wwi:sales_order:66823 and wwi:sales_order:57891. "
        "Compare their dates, source statuses, all line quantities and amounts, "
        "and explicitly identify unknown delivery information.",
        Counter({"get_customer_overview": 1, "get_sales_order": 2}),
        ("66823", "57891", "Delivered", "unknown"),
    ),
    Case(
        "zero_order_scope",
        "First summarize authorized customer and order counts, then look up "
        "customers wwi:organization:customer:60 and wwi:organization:customer:88. "
        "Explain why neither has orders in the current dataset and why that "
        "does not establish an absence of orders in the full WWI database.",
        Counter({"get_customer_portfolio_summary": 1, "get_customer_overview": 2}),
        ("60", "88", "current dataset", "full source history"),
    ),
    Case(
        "cross_domain",
        "Show customer wwi:organization:customer:65 and supplier "
        "wwi:organization:supplier:7 with all their orders. Open sales order "
        "wwi:sales_order:66823 and purchase order wwi:purchase_order:2044. "
        "Compare sales picking/delivery and purchasing outer-pack/base-unit "
        "semantics, currency assumptions, source statuses, and native statuses.",
        Counter(
            {
                "get_customer_overview": 1,
                "get_supplier_overview": 1,
                "get_sales_order": 1,
                "get_purchase_order": 1,
            }
        ),
        ("66823", "2044", "Delivered", "Base quantity", "Native document status"),
    ),
)


def run_case(base_url: str, timeout: float, case: Case) -> dict[str, object]:
    payload = {
        "threadId": f"complex-{case.name}-{uuid.uuid4()}",
        "runId": f"run-{uuid.uuid4()}",
        "state": {},
        "context": [],
        "forwardedProps": {},
        "tools": [],
        "messages": [
            {"id": f"user-{uuid.uuid4()}", "role": "user", "content": case.prompt}
        ],
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/agent",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    active: set[str] = set()
    ended: set[str] = set()
    results: set[str] = set()
    violations: list[str] = []
    errors: list[str] = []
    tools: list[str] = []
    answer: list[str] = []
    finished = False
    started_at = time.monotonic()

    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            kind = event.get("type")
            call_id = event.get("toolCallId")
            if kind == "TOOL_CALL_START":
                if call_id in active or call_id in ended:
                    violations.append(f"duplicate start: {call_id}")
                active.add(call_id)
                tools.append(event.get("toolCallName"))
            elif kind == "TOOL_CALL_ARGS" and call_id not in active:
                violations.append(f"arguments without active call: {call_id}")
            elif kind == "TOOL_CALL_END":
                if call_id not in active:
                    violations.append(f"end without active call: {call_id}")
                active.discard(call_id)
                ended.add(call_id)
            elif kind == "TOOL_CALL_RESULT":
                if call_id not in ended:
                    violations.append(f"result before end: {call_id}")
                results.add(call_id)
            elif kind == "TEXT_MESSAGE_CONTENT":
                answer.append(event.get("delta", ""))
            elif kind == "RUN_FINISHED":
                finished = True
            elif kind == "RUN_ERROR":
                errors.append(event.get("message", "run error"))

    answer_text = "".join(answer)
    missing_markers = [
        marker for marker in case.answer_markers if marker not in answer_text
    ]
    if active:
        violations.append(f"active calls at terminal event: {sorted(active)}")
    if ended != results:
        violations.append(
            f"tool result mismatch: ended={len(ended)}, results={len(results)}"
        )
    actual_tools = Counter(tools)
    passed = (
        status == 200
        and finished
        and not errors
        and not violations
        and actual_tools == case.expected_tools
        and not missing_markers
    )
    return {
        "case": case.name,
        "passed": passed,
        "http_status": status,
        "seconds": round(time.monotonic() - started_at, 2),
        "finished": finished,
        "tools": dict(actual_tools),
        "errors": errors,
        "protocol_violations": violations,
        "missing_answer_markers": missing_markers,
        "answer_characters": len(answer_text),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3100")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    results = [run_case(args.base_url, args.timeout, case) for case in CASES]
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    passed = sum(bool(result["passed"]) for result in results)
    print(f"complex demo cases: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
