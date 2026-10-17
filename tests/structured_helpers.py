"""Protocol helpers for mock models; gold expectations live in test cases."""

import json

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall


def plan_for_messages(messages, *, field=None, language="en"):
    returns = [
        p
        for p in messages[-1].parts
        if isinstance(p, ToolReturnPart) and isinstance(p.content, dict)
    ]
    if not returns:
        return {"language": language, "notice": "needs_details"}
    facts, tables = [], []
    for part in returns:
        evidence = part.content.get("answer_evidence", {})
        facts.extend(
            f["id"]
            for f in evidence.get("facts", [])
            if field is None or f["field"] == field
        )
        if field is None:
            tables.extend({"table_id": t["id"]} for t in evidence.get("tables", []))
    return {"language": language, "facts": facts, "tables": tables}


def output_response(messages, **kwargs):
    return ModelResponse(
        parts=[
            ToolCallPart(
                "present_answer",
                {"plan": plan_for_messages(messages, **kwargs)},
                "output",
            )
        ]
    )


def output_delta(messages, **kwargs):
    return {
        0: DeltaToolCall(
            name="present_answer",
            json_args=json.dumps({"plan": plan_for_messages(messages, **kwargs)}),
            tool_call_id="output",
        )
    }
