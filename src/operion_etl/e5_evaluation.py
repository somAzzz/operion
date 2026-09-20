from __future__ import annotations

import argparse
import io
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .e3_evaluation import RecordingResult


class StrictEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityEvidence(StrictEvidence):
    provider: str = Field(min_length=1)
    pilot_users: int = Field(ge=3, le=5)
    one_company: bool
    revocation_minutes: float = Field(ge=0, le=5)
    cross_scope_denied: bool


class SecretsEvidence(StrictEvidence):
    rotation_passed: bool
    old_credential_rejected: bool
    private_services_unreachable: bool
    repository_scan_passed: bool


class DependencyEvidence(StrictEvidence):
    model_outage_degraded: bool
    twenty_outage_degraded: bool
    erpnext_outage_degraded: bool
    no_unknown_write_retry: bool


class AlertEvidence(StrictEvidence):
    postgres_failure_received: bool
    worker_stall_received: bool
    disk_low_received: bool
    primary_contact: str = Field(min_length=1)
    backup_contact: str = Field(min_length=1)


class RecoveryEvidence(StrictEvidence):
    encrypted: bool
    off_host: bool
    restore_passed: bool
    rpo_minutes: float = Field(ge=0, le=15)
    rto_minutes: float = Field(ge=0, le=240)
    remote_reconciled_before_resume: bool
    old_approvals_not_replayed: bool


class CapacityEvidence(StrictEvidence):
    concurrent_sessions: int = Field(ge=5)
    read_p95_seconds: float = Field(gt=0, le=5)
    agent_p95_seconds: float = Field(gt=0, le=60)
    task_p95_seconds: float = Field(gt=0, le=30)
    overload_controlled: bool


class ReleaseEvidence(StrictEvidence):
    rollback_passed: bool
    previous_release_healthy: bool
    migrations_compatible: bool
    full_regression_passed: bool


class LifecycleEvidence(StrictEvidence):
    raw_content_hours: int = Field(ge=1, le=24)
    diagnostic_log_days: int = Field(ge=1, le=14)
    trace_days: int = Field(ge=1, le=7)
    action_event_days: int = Field(ge=180)
    deletion_drill_passed: bool
    access_audit_passed: bool


class PilotEvidence(StrictEvidence):
    business_days: int = Field(ge=10)
    legitimate_requests: int = Field(ge=0)
    unresolved_blockers: int = Field(ge=0, le=0)
    business_signoff: str = Field(min_length=1)
    operations_signoff: str = Field(min_length=1)
    governance_signoff: str = Field(min_length=1)


class E5Evidence(StrictEvidence):
    schema_version: str
    environment: str
    window_start: datetime
    window_end: datetime
    identity: IdentityEvidence
    secrets: SecretsEvidence
    dependencies: DependencyEvidence
    alerts: AlertEvidence
    recovery: RecoveryEvidence
    capacity: CapacityEvidence
    release: ReleaseEvidence
    lifecycle: LifecycleEvidence
    pilot: PilotEvidence


CASE_FIELDS = {
    "O01": "identity",
    "O02": "secrets",
    "O03": "dependencies",
    "O04": "alerts",
    "O05": "recovery",
    "O06": "capacity",
    "O07": "release",
    "O08": "lifecycle",
}


def evidence_blockers(evidence: E5Evidence) -> list[str]:
    blockers: list[str] = []
    if evidence.schema_version != "operion-e5-evidence-v1":
        blockers.append("unsupported evidence schema")
    if evidence.environment.lower() in {"local", "test", "demo", "simulated"}:
        blockers.append(
            "enterprise pilot evidence cannot come from a simulated environment"
        )
    if "replace-with" in json.dumps(evidence.model_dump(mode="json")):
        blockers.append("evidence still contains template placeholders")
    if evidence.window_end <= evidence.window_start:
        blockers.append("pilot observation window is invalid")
    if evidence.window_end.astimezone(UTC) > datetime.now(UTC):
        blockers.append("pilot observation window has not completed")
    day = evidence.window_start.date()
    end = evidence.window_end.date()
    business_days = 0
    while day <= end:
        if day.weekday() < 5:
            business_days += 1
        day += timedelta(days=1)
    if business_days < evidence.pilot.business_days:
        blockers.append("observation window does not contain the claimed business days")
    if evidence.pilot.legitimate_requests == 0:
        blockers.append("pilot has no legitimate traffic")
    document = evidence.model_dump()
    for section_name in CASE_FIELDS.values():
        for field_name, value in document[section_name].items():
            if isinstance(value, bool) and not value:
                blockers.append(f"{section_name}.{field_name} is not proven")
    return blockers


def evaluate(evidence_path: Path, output: Path) -> dict[str, Any]:
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    stream = io.StringIO()
    result: RecordingResult = unittest.TextTestRunner(
        stream=stream, verbosity=2, resultclass=RecordingResult
    ).run(suite)
    blockers: list[str] = []
    evidence: E5Evidence | None = None
    try:
        evidence = E5Evidence.model_validate_json(evidence_path.read_text())
        blockers.extend(evidence_blockers(evidence))
    except (OSError, ValidationError, ValueError) as error:
        blockers.append(f"external evidence is incomplete: {error}")

    if not result.wasSuccessful():
        blockers.append("deterministic regression suite failed")
    cases = {
        case_id: {
            "status": "passed" if evidence is not None and not blockers else "blocked",
            "evidence_section": field,
        }
        for case_id, field in CASE_FIELDS.items()
    }
    passed = evidence is not None and result.wasSuccessful() and not blockers
    report = {
        "report_version": "operion-e5-evaluation-v1",
        "status": "passed" if passed else "blocked",
        "completed_at": datetime.now(UTC).isoformat(),
        "tests": {
            "status": "passed" if result.wasSuccessful() else "failed",
            "count": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
        },
        "cases": cases,
        "pilot": (
            {
                "business_days": evidence.pilot.business_days,
                "legitimate_requests": evidence.pilot.legitimate_requests,
                "window_start": evidence.window_start.isoformat(),
                "window_end": evidence.window_end.isoformat(),
            }
            if evidence
            else None
        ),
        "blockers": blockers,
        "raw_test_output": stream.getvalue(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-evaluate-e5")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.evidence, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "tests": report["tests"]["count"],
                "cases": len(report["cases"]),
                "blockers": len(report["blockers"]),
            }
        )
    )
    if report["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
