"""Run destructive action-control tests only against a disposable test database."""

from __future__ import annotations

import os
import sys
import unittest
from urllib.parse import urlparse

dsn = os.environ.get("OPERION_TEST_ACTION_DATABASE_URL", "")
database = urlparse(dsn).path.lstrip("/")
if not dsn or not database.endswith("_test"):
    raise SystemExit(
        "OPERION_TEST_ACTION_DATABASE_URL must name a disposable database ending _test"
    )

suite = unittest.TestSuite(
    unittest.defaultTestLoader.discover("tests", pattern=pattern)
    for pattern in ("test_action_control.py", "test_action_app.py")
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    raise SystemExit(f"database tests skipped unexpectedly: {result.skipped}")
if not result.wasSuccessful():
    sys.exit(1)
