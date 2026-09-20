from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from operion_etl.e5_evaluation import E5Evidence, evidence_blockers


def valid_evidence() -> dict:
    start = datetime(2026, 9, 1, 8, tzinfo=UTC)
    return {
        "schema_version": "operion-e5-evidence-v1",
        "environment": "enterprise-pilot-eu",
        "window_start": start,
        "window_end": start + timedelta(days=13),
        "identity": {
            "provider": "company-oidc",
            "pilot_users": 3,
            "one_company": True,
            "revocation_minutes": 1,
            "cross_scope_denied": True,
        },
        "secrets": {
            "rotation_passed": True,
            "old_credential_rejected": True,
            "private_services_unreachable": True,
            "repository_scan_passed": True,
        },
        "dependencies": {
            "model_outage_degraded": True,
            "twenty_outage_degraded": True,
            "erpnext_outage_degraded": True,
            "no_unknown_write_retry": True,
        },
        "alerts": {
            "postgres_failure_received": True,
            "worker_stall_received": True,
            "disk_low_received": True,
            "primary_contact": "primary@example.test",
            "backup_contact": "backup@example.test",
        },
        "recovery": {
            "encrypted": True,
            "off_host": True,
            "restore_passed": True,
            "rpo_minutes": 10,
            "rto_minutes": 30,
            "remote_reconciled_before_resume": True,
            "old_approvals_not_replayed": True,
        },
        "capacity": {
            "concurrent_sessions": 5,
            "read_p95_seconds": 1,
            "agent_p95_seconds": 10,
            "task_p95_seconds": 2,
            "overload_controlled": True,
        },
        "release": {
            "rollback_passed": True,
            "previous_release_healthy": True,
            "migrations_compatible": True,
            "full_regression_passed": True,
        },
        "lifecycle": {
            "raw_content_hours": 24,
            "diagnostic_log_days": 14,
            "trace_days": 7,
            "action_event_days": 180,
            "deletion_drill_passed": True,
            "access_audit_passed": True,
        },
        "pilot": {
            "business_days": 10,
            "legitimate_requests": 100,
            "unresolved_blockers": 0,
            "business_signoff": "business-owner",
            "operations_signoff": "operations-owner",
            "governance_signoff": "governance-owner",
        },
    }


class E5EvaluationTests(unittest.TestCase):
    def test_complete_real_pilot_evidence_passes_gate(self):
        evidence = E5Evidence.model_validate(valid_evidence())
        self.assertEqual([], evidence_blockers(evidence))

    def test_simulated_or_unreceived_controls_cannot_pass(self):
        document = valid_evidence()
        document["environment"] = "simulated"
        document["alerts"]["disk_low_received"] = False
        blockers = evidence_blockers(E5Evidence.model_validate(document))
        self.assertTrue(any("simulated" in item for item in blockers))
        self.assertTrue(any("disk_low_received" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()
