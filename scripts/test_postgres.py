"""Create an isolated PostgreSQL container; never accept an existing test DSN."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from database_guard import owned_database  # noqa: E402


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> int:
    # A caller-supplied URL is deliberately not used, even if named *_test.
    os.environ.pop("OPERION_TEST_ACTION_DATABASE_URL", None)
    name = "operion-test-" + uuid4().hex
    password = secrets.token_hex(24)
    container = None
    try:
        env = dict(os.environ, POSTGRES_PASSWORD=password)
        container = subprocess.check_output(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--label",
                f"operion.test-owner={name}",
                "--publish",
                "127.0.0.1::5432",
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_DB=operion_test",
                "postgres:16",
            ],
            text=True,
            env=env,
        ).strip()
        port = docker("port", container, "5432/tcp").rsplit(":", 1)[1]
        dsn = f"postgresql://postgres:{password}@127.0.0.1:{port}/operion_test"
        deadline = time.monotonic() + 60
        while True:
            try:
                with psycopg.connect(dsn, connect_timeout=2):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "isolated PostgreSQL did not become ready"
                    ) from None
                time.sleep(0.25)
        os.environ["OPERION_TEST_ACTION_DATABASE_URL"] = dsn
        with owned_database(dsn):
            suite = unittest.TestSuite(
                unittest.defaultTestLoader.discover(
                    str(ROOT / "tests"), pattern=pattern
                )
                for pattern in ("test_action_control.py", "test_action_app.py")
            )
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() and not result.skipped else 1
    finally:
        os.environ.pop("OPERION_TEST_ACTION_DATABASE_URL", None)
        if container:
            owner = docker(
                "inspect",
                "--format",
                '{{index .Config.Labels "operion.test-owner"}}',
                container,
            )
            if owner != name:
                raise RuntimeError("refusing cleanup: container ownership mismatch")
            docker("rm", "--force", container)


if __name__ == "__main__":
    raise SystemExit(main())
