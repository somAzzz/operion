"""Read back one Web-to-Agent trace, including pagination and content checks.

Uses the existing project's read API. Never prints credentials or prompt text.
The optional output file contains the fetched trace content and is local evidence.
"""

from __future__ import annotations

import argparse
import base64
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from operion_etl.twenty import read_env


def fetch_observations(env: dict[str, str], trace_id: str, since: str) -> list[dict]:
    auth = base64.b64encode(
        f"{env['LANGFUSE_PUBLIC_KEY']}:{env['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()
    params = {
        "traceId": trace_id,
        "fromStartTime": since,
        "toStartTime": datetime.now(UTC).isoformat(),
        "fields": "core,basic,usage,metadata,io,model,trace_context",
        "limit": 1000,
    }
    rows = []
    seen = set()
    for _ in range(100):
        url = (
            env["LANGFUSE_BASE_URL"].rstrip("/")
            + "/api/public/v2/observations?"
            + urllib.parse.urlencode(params)
        )
        request = urllib.request.Request(
            url, headers={"Authorization": "Basic " + auth}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        rows.extend(result["data"])
        cursor = result.get("meta", {}).get("cursor")
        if not cursor:
            return rows
        if cursor in seen:
            raise RuntimeError("Observation pagination repeated a cursor")
        seen.add(cursor)
        params["cursor"] = cursor
    raise RuntimeError("Observation pagination exceeded safety bound")


def checks(
    rows: list[dict], *, environment: str, release: str, content: bool
) -> dict[str, bool]:
    ids = {row["id"] for row in rows}
    runs = [row for row in rows if row["name"] == "operion.agent.run"]
    generations = [row for row in rows if row["type"] == "GENERATION"]
    tools = [row for row in rows if row["type"] == "TOOL"]
    services = {
        row.get("metadata", {}).get("resourceAttributes.service.name") for row in rows
    }
    results = {
        "one_business_run": len(runs) == 1,
        "web_and_agent": {"operion-web", "operion-agent"} <= services,
        "one_root": sum(not row.get("parentObservationId") for row in rows) == 1,
        "no_missing_parents": all(
            not row.get("parentObservationId") or row["parentObservationId"] in ids
            for row in rows
        ),
        "model_and_tool_observations": bool(generations and tools),
        "token_usage": bool(generations)
        and all(row.get("totalUsage", 0) > 0 for row in generations),
        "consistent_environment": bool(rows)
        and all(row["environment"] == environment for row in rows),
        "consistent_release": bool(rows)
        and all(row["version"] == release for row in rows),
        "no_transport_noise": not any(
            row["name"].endswith(("http send", "http receive")) for row in rows
        ),
        "successful_business_status": len(runs) == 1
        and runs[0].get("metadata", {}).get("run_status") == "succeeded"
        and runs[0]["level"] == "DEFAULT",
    }
    if content:
        results["prompt_response_and_tool_content"] = bool(
            generations and tools and runs
        ) and all(
            row.get("input") and row.get("output") for row in generations + tools + runs
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env.langfuse.local"))
    parser.add_argument("--environment", default="development")
    parser.add_argument("--release", required=True)
    parser.add_argument("--require-content", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = fetch_observations(read_env(args.env_file), args.trace_id, args.since)
    results = checks(
        rows,
        environment=args.environment,
        release=args.release,
        content=args.require_content,
    )
    report = {
        "trace_id": args.trace_id,
        "observation_count": len(rows),
        "checks": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report | {"observations": rows}, ensure_ascii=False, indent=2)
        )
    print(json.dumps(report, indent=2))
    if not all(results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
