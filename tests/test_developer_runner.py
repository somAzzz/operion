import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DeveloperRunnerTests(unittest.TestCase):
    def run_worker(self, test):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            process = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify_cases.py",
                    "--worker",
                    test,
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                env=dict(
                    os.environ,
                    OPERION_TEST_ACTION_DATABASE_URL="postgresql://invalid/test",
                ),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return process.returncode, json.loads(output.read_text())

    def test_worker_failure_is_nonzero_with_evidence(self):
        code, result = self.run_worker(
            "test_database_guard.DatabaseIsolationTests.missing_case"
        )
        self.assertNotEqual(0, code)
        self.assertEqual("FAIL", result["status"])
        self.assertTrue(result["errors"])

    def test_required_skips_cannot_pass_and_inherited_dsn_is_unused(self):
        code, result = self.run_worker("test_action_app.ActionAppTests")
        self.assertNotEqual(0, code)
        self.assertEqual("SKIP", result["status"])
        self.assertEqual(result["tests"], len(result["skipped"]))

    def test_unknown_layer_combination_is_not_a_successful_empty_run(self):
        process = subprocess.run(
            [sys.executable, "scripts/verify_cases.py", "cancel", "--layer", "mcp"],
            cwd=ROOT,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(2, process.returncode)
