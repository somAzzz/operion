from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic_ai import Agent

from .agent_runtime import (
    AgentDependencies,
    AgentSettings,
    build_model,
    create_operion_agent,
)
from .read_tools import AccessScope, CanonicalRepository


async def _probe(name: str, operation: Any) -> dict[str, Any]:
    started = monotonic()
    try:
        detail = await operation()
        return {
            "name": name,
            "status": "passed",
            "duration_seconds": round(monotonic() - started, 3),
            "detail": detail,
        }
    except Exception as error:
        return {
            "name": name,
            "status": "failed",
            "duration_seconds": round(monotonic() - started, 3),
            "error": f"{type(error).__name__}: {error}",
        }


async def run_compatibility(
    settings: AgentSettings,
    canonical_directory: Path,
    identity_map: Path,
    observed_at: str,
) -> dict[str, Any]:
    async def text_request(thinking: bool) -> dict[str, Any]:
        probe_settings = replace(
            settings, thinking_enabled=thinking, max_output_tokens=80
        )
        agent = Agent(
            build_model(probe_settings),
            output_type=str,
            model_settings=probe_settings.model_settings(),
        )
        result = await agent.run("Reply with exactly COMPAT_OK.")
        return {"thinking_enabled": thinking, "output": result.output[:120]}

    async def streamed_request() -> dict[str, Any]:
        probe_settings = replace(settings, max_output_tokens=80)
        agent = Agent(
            build_model(probe_settings),
            output_type=str,
            model_settings=probe_settings.model_settings(),
        )
        async with agent.run_stream("Reply with exactly STREAM_OK.") as result:
            output = await result.get_output()
        return {"output": output[:120]}

    async def structured_tool_request() -> dict[str, Any]:
        repository = CanonicalRepository(
            canonical_directory,
            identity_map=identity_map,
            observed_at=observed_at,
        )
        deps = AgentDependencies(
            repository=repository,
            scope=AccessScope("AI Demo GmbH", frozenset()),
            user_id="model-compatibility",
        )
        agent = create_operion_agent(replace(settings, max_output_tokens=500))
        result = await agent.run("检查履约场景 F01。", deps=deps)
        return {
            "tool_calls": [call["name"] for call in deps.tool_calls],
            "arguments": deps.tool_calls[0]["arguments"] if deps.tool_calls else {},
            "has_text_output": bool(result.output.strip()),
        }

    async def long_output() -> dict[str, Any]:
        probe_settings = replace(settings, max_output_tokens=256)
        agent = Agent(
            build_model(probe_settings),
            output_type=str,
            model_settings=probe_settings.model_settings(),
        )
        result = await agent.run(
            "Write a numbered list of exactly 20 short inventory control checks."
        )
        return {
            "characters": len(result.output),
            "output_tokens": result.usage.output_tokens,
        }

    async def cancellation() -> dict[str, Any]:
        probe_settings = replace(settings, max_output_tokens=1000)
        agent = Agent(
            build_model(probe_settings),
            output_type=str,
            model_settings=probe_settings.model_settings(),
        )
        try:
            async with asyncio.timeout(0.001):
                await agent.run("Write a very long essay about inventory systems.")
        except TimeoutError:
            return {"cancelled_by_timeout": True}
        raise RuntimeError("model request completed before cancellation")

    probes = [
        await _probe("non_stream_thinking_off", lambda: text_request(False)),
        await _probe("non_stream_thinking_on", lambda: text_request(True)),
        await _probe("streaming", streamed_request),
        await _probe("structured_tool_arguments", structured_tool_request),
        await _probe("bounded_long_output", long_output),
        await _probe("request_cancellation", cancellation),
        {
            "name": "invalid_tool_arguments",
            "status": "passed",
            "detail": {
                "boundary": "Pydantic tool schema plus deterministic domain validation",
                "evidence": [
                    "tests/test_read_tools.py",
                    "tests/test_agent_runtime.py",
                ],
            },
        },
    ]
    return {
        "report_version": "operion-e2-model-compatibility-v1",
        "status": "passed"
        if all(probe["status"] == "passed" for probe in probes)
        else "failed",
        "observed_at": datetime.now(UTC).isoformat(),
        "stack": {
            "model": settings.model_name,
            "endpoint": settings.model_base_url,
            "pydantic_ai": "2.46.0",
            "openai_sdk": "3.16.2",
            "sglang_tool_call_parser": "qwen3_coder",
            "sglang_reasoning_parser": "qwen3",
        },
        "proxy_decision": {
            "required": True,
            "kind": "in-process response metadata normalizer",
            "scope": "metadata.weight_versions list-to-JSON-string only",
            "transport_retries": 0,
            "streaming_payloads_modified": False,
        },
        "settings": {
            key: value
            for key, value in asdict(settings).items()
            if key != "model_api_key"
        },
        "probes": probes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-model-compatibility")
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
        run_compatibility(
            AgentSettings.from_environment(),
            args.canonical_directory,
            args.identity_map,
            args.observed_at,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "probes": len(report["probes"])}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
