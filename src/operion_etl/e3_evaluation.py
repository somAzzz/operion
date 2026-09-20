from __future__ import annotations

import argparse
import io
import json
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

CASE_TESTS = {
    "W01": "test_w01_unapproved_and_forged_approval_do_not_execute",
    "W02": "test_w02_revision_invalidates_old_approval",
    "W03": "test_w03_expiry_revocation_and_cross_tenant_replay",
    "W04": "test_w04_preflight_detects_revoked_owner_and_invalid_assignee",
    "W05": "test_w05_concurrent_proposal_and_workers_have_one_effect",
    "W06": "test_w06_response_loss_enters_unknown_then_reconciles",
    "W07": "test_w07_w09_crash_and_expired_lease_reconcile_without_reclaim",
    "W08": "test_w08_proven_before_send_failure_is_safely_retried",
    "W09": "test_w07_w09_crash_and_expired_lease_reconcile_without_reclaim",
    "W10": "test_w10_changed_target_version_blocks_send",
    "W11": "test_w11_pause_and_cancel_do_not_misreport_inflight_action",
    "W12": "test_w12_strict_schema_and_scope_reject_invalid_input",
    "W13": "test_w13_database_failure_prevents_new_action",
    "W14": "test_w14_multiple_remote_matches_require_manual_review",
    "W15": "test_w15_success_and_compensation_are_separate_actions",
}


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.statuses: dict[str, dict[str, str]] = {}

    @staticmethod
    def _name(test: unittest.TestCase) -> str:
        return test.id().rsplit(".", 1)[-1]

    def addSuccess(self, test):
        super().addSuccess(test)
        self.statuses[self._name(test)] = {"status": "passed"}

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.statuses[self._name(test)] = {
            "status": "failed",
            "error": self._exc_info_to_string(err, test),
        }

    def addError(self, test, err):
        super().addError(test, err)
        self.statuses[self._name(test)] = {
            "status": "failed",
            "error": self._exc_info_to_string(err, test),
        }

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.statuses[self._name(test)] = {"status": "skipped", "reason": reason}


def evaluate(dsn: str, output: Path) -> dict:
    os.environ["OPERION_TEST_ACTION_DATABASE_URL"] = dsn
    suite = unittest.defaultTestLoader.discover(
        "tests", pattern="test_action_control.py"
    )
    stream = io.StringIO()
    runner = unittest.TextTestRunner(
        stream=stream,
        verbosity=2,
        resultclass=RecordingResult,
    )
    result: RecordingResult = runner.run(suite)
    cases = {
        case_id: result.statuses.get(
            test_name, {"status": "failed", "error": "test did not run"}
        )
        for case_id, test_name in CASE_TESTS.items()
    }
    report = {
        "report_version": "operion-e3-action-control-evaluation-v1",
        "status": "passed"
        if result.wasSuccessful()
        and all(case["status"] == "passed" for case in cases.values())
        else "failed",
        "completed_at": datetime.now(UTC).isoformat(),
        "database": "PostgreSQL 16 isolated test instance",
        "target": "persistent E3 idempotent stub; no Twenty/ERPNext write",
        "cases": cases,
        "test_count": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "raw_test_output": stream.getvalue(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="operion-evaluate-e3")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("OPERION_TEST_ACTION_DATABASE_URL", ""),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit(
            "--database-url or OPERION_TEST_ACTION_DATABASE_URL is required"
        )
    report = evaluate(args.database_url, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "cases": len(report["cases"]),
                "tests": report["test_count"],
            }
        )
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
