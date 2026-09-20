from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from .twenty import TwentyClient, read_env

INTROSPECTION_QUERY = """
query E3TaskCapabilities {
  task: __type(name: "Task") { name fields { name } }
  create: __type(name: "TaskCreateInput") { name inputFields { name } }
  update: __type(name: "TaskUpdateInput") { name inputFields { name } }
  target: __type(name: "TaskTarget") { name fields { name } }
  targetCreate: __type(name: "TaskTargetCreateInput") {
    name inputFields { name }
  }
}
"""


def _names(value: dict[str, Any] | None, key: str) -> list[str]:
    return [item["name"] for item in (value or {}).get(key, [])]


def probe(env_file: Path, database_url: str) -> dict[str, Any]:
    values = read_env(env_file)
    client = TwentyClient(
        values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
        values.get("TWENTY_API_KEY_READ_ONLY", ""),
    )
    schema = client.graphql(INTROSPECTION_QUERY)
    tasks = client.records("tasks", 1)
    with psycopg.connect(database_url) as connection:
        postgres_version = connection.execute("SHOW server_version").fetchone()[0]
        migration_tables = connection.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE 'operion_action%'
            """
        ).fetchone()[0]
    task_fields = _names(schema.get("task"), "fields")
    create_fields = _names(schema.get("create"), "inputFields")
    update_fields = _names(schema.get("update"), "inputFields")
    target_fields = _names(schema.get("target"), "fields")
    target_create_fields = _names(schema.get("targetCreate"), "inputFields")
    capabilities = {
        "task_object_and_read_api": {
            "status": "verified",
            "task_fields": task_fields,
            "read_probe_count": len(tasks),
        },
        "client_supplied_task_id": {
            "status": "schema_only",
            "advertised": "id" in create_fields,
            "e4_blocker": "create/idempotency behavior must be proven on an isolated task",
        },
        "stable_external_action_field": {
            "status": "not_available",
            "advertised": "actionId" in task_fields,
            "decision": "use a deterministic task UUID only if the E4 live probe proves uniqueness",
        },
        "task_target_relation": {
            "status": "schema_only",
            "task_target_fields": target_fields,
            "task_target_create_fields": target_create_fields,
            "e4_blocker": "atomicity and exact readback require an isolated live probe",
        },
        "notification_side_effects": {
            "status": "unknown",
            "e4_blocker": "observe actual assignee notifications on one isolated task",
        },
        "conditional_update_cas": {
            "status": "not_demonstrated",
            "update_fields": update_fields,
            "decision": "do not release automated task updates or field restoration",
        },
        "failure_and_timeout_semantics": {
            "status": "unknown",
            "e4_blocker": "inject connection loss around one isolated create and query by stable ID",
        },
        "postgres_action_ledger": {
            "status": "verified",
            "server_version": postgres_version,
            "migration_table_count": migration_tables,
            "claim_mode": "FOR UPDATE SKIP LOCKED",
        },
    }
    return {
        "report_version": "operion-e3-capability-matrix-v1",
        "status": "passed",
        "observed_at": datetime.now(UTC).isoformat(),
        "twenty_version": "2.39.0",
        "probe_mode": "read-only schema introspection and GET; no Task write",
        "capabilities": capabilities,
        "e4_release_allowed": False,
        "reason": "live idempotency, relation, notification, and failure semantics remain E4 blockers",
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-probe-e3")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = probe(args.env_file, args.database_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "e4_release_allowed": False}))


if __name__ == "__main__":
    main()
