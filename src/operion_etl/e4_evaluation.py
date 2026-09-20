from __future__ import annotations

import argparse
import io
import json
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from .e3_evaluation import RecordingResult

CASE_TESTS = {
    "W01": ["test_w01_unapproved_and_forged_approval_do_not_execute"],
    "W02": ["test_w02_revision_invalidates_old_approval"],
    "W03": ["test_w03_expiry_revocation_and_cross_tenant_replay"],
    "W04": ["test_w04_preflight_detects_revoked_owner_and_invalid_assignee"],
    "W05": ["test_w05_concurrent_proposal_and_workers_have_one_effect"],
    "W06": ["test_e4_response_loss_reconciles_same_twenty_task"],
    "W07": ["test_w07_w09_crash_and_expired_lease_reconcile_without_reclaim"],
    "W08": ["test_w08_proven_before_send_failure_is_safely_retried"],
    "W09": ["test_w07_w09_crash_and_expired_lease_reconcile_without_reclaim"],
    "W10": ["test_preflight_detects_version_and_identity_changes"],
    "W11": ["test_w11_pause_and_cancel_do_not_misreport_inflight_action"],
    "W12": [
        "test_w12_strict_schema_and_scope_reject_invalid_input",
        "test_existing_deterministic_id_with_other_content_is_manual_review",
    ],
    "W13": ["test_w13_database_failure_prevents_new_action"],
    "W14": ["test_w14_multiple_remote_matches_require_manual_review"],
    "W15": ["test_w15_success_and_compensation_are_separate_actions"],
}


def evaluate(dsn: str, live_report_path: Path, output: Path) -> dict:
    os.environ["OPERION_TEST_ACTION_DATABASE_URL"] = dsn
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    stream = io.StringIO()
    result: RecordingResult = unittest.TextTestRunner(
        stream=stream,
        verbosity=2,
        resultclass=RecordingResult,
    ).run(suite)
    cases = {}
    for case_id, tests in CASE_TESTS.items():
        statuses = [
            result.statuses.get(
                test_name, {"status": "failed", "error": "test did not run"}
            )
            for test_name in tests
        ]
        cases[case_id] = {
            "status": (
                "passed"
                if all(status["status"] == "passed" for status in statuses)
                else "failed"
            ),
            "tests": tests,
        }
    live = json.loads(live_report_path.read_text())
    live_passed = (
        live.get("status") == "passed"
        and live.get("response_loss", {}).get("reconciliation", {}).get("status")
        == "succeeded"
        and all(
            live.get("checks", {}).get(key) is expected
            for key, expected in {
                "separate_proposer_approver": True,
                "deterministic_task_id_equals_action_id": True,
                "exact_task_and_company_target_readback": True,
                "blind_retry_used": False,
                "one_worker_claimed": True,
            }.items()
        )
    )
    passed = (
        result.wasSuccessful()
        and all(case["status"] == "passed" for case in cases.values())
        and live_passed
    )
    report = {
        "report_version": "operion-e4-followup-evaluation-v1",
        "status": "passed" if passed else "failed",
        "completed_at": datetime.now(UTC).isoformat(),
        "cases": cases,
        "test_count": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "live_twenty_fault_evaluation": {
            "status": "passed" if live_passed else "failed",
            "path": str(live_report_path),
        },
        "target": "Twenty internal Task create only; no customer/order mutation",
        "raw_test_output": stream.getvalue(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-evaluate-e4")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("OPERION_TEST_ACTION_DATABASE_URL", ""),
    )
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit(
            "--database-url or OPERION_TEST_ACTION_DATABASE_URL is required"
        )
    report = evaluate(args.database_url, args.live_report, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "cases": len(report["cases"]),
                "tests": report["test_count"],
                "live": report["live_twenty_fault_evaluation"]["status"],
            }
        )
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
