#!/usr/bin/env python3
"""Run five read-only interview cases through Web, AG-UI, Agent, and tools."""

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
        "查找名称包含 Tailspin Toys 的客户。我选择 "
        "wwi:organization:customer:65，请显示客户、联系人和全部订单。打开销售"
        "订单 wwi:sales_order:66823，逐行解释订购、已拣、未拣和交付数量，并说明"
        "为什么已拣不能证明已交付。",
        Counter(
            {
                "search_customers": 1,
                "get_customer_overview": 1,
                "get_sales_order": 1,
            }
        ),
        ("66823", "已拣", "交付", "未知"),
    ),
    Case(
        "supplier_chain",
        "查找名称包含 Litware 的供应商。我选择 wwi:organization:supplier:7，请显示"
        "供应商和全部采购订单。打开采购订单 wwi:purchase_order:2044，逐行说明"
        "外包装数量、每包装基础单位数、基础数量、基础单位价格和行金额，并核对总额。",
        Counter(
            {
                "search_suppliers": 1,
                "get_supplier_overview": 1,
                "get_purchase_order": 1,
            }
        ),
        ("2044", "基础", "75,620.00", "723,322.40"),
    ),
    Case(
        "two_order_compare",
        "查看客户 wwi:organization:customer:65 的资料和全部订单，然后分别打开销售"
        "订单 wwi:sales_order:66823 与 wwi:sales_order:57891，比较两张订单的日期、"
        "源状态、所有明细数量和金额，并明确哪些交付信息未知。",
        Counter({"get_customer_overview": 1, "get_sales_order": 2}),
        ("66823", "57891", "交付", "未知"),
    ),
    Case(
        "zero_order_scope",
        "先汇总当前授权客户数量和订单数量，再分别查看客户 "
        "wwi:organization:customer:60 与 wwi:organization:customer:88。解释两者为什么"
        "没有订单，以及为什么不能据此声称它们在完整 WWI 数据库中没有订单。",
        Counter({"get_customer_portfolio_summary": 1, "get_customer_overview": 2}),
        ("60", "88", "当前", "完整 WWI"),
    ),
    Case(
        "cross_domain",
        "同时查看客户 wwi:organization:customer:65 和供应商 "
        "wwi:organization:supplier:7 的资料及全部订单；再打开销售订单 "
        "wwi:sales_order:66823 和采购订单 wwi:purchase_order:2044，比较销售拣货/"
        "交付语义与采购外包装/基础单位语义、币种假设、源状态和原生状态。",
        Counter(
            {
                "get_customer_overview": 1,
                "get_supplier_overview": 1,
                "get_sales_order": 1,
                "get_purchase_order": 1,
            }
        ),
        ("66823", "2044", "交付", "基础", "原生状态"),
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
    print(f"complex interview cases: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
