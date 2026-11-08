import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gateway_release", ROOT / "scripts/deploy_gateway_release.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
REVISION = "a" * 40
REPOSITORY = "Owner/Operion"


class GatewayReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.runtime = self.directory / "runtime"
        for name in ("tls/ca.crt", "policy/identity-policy.json"):
            path = self.runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic")
        self.env_file = self.directory / "telemetry.env"
        self.env_file.write_text("OPERION_OTEL_ENABLED=1\n")
        for service in ("agent", "web"):
            self.record(service)

    def record(self, service_name, **changes):
        record = {
            "revision": REVISION,
            "service": service_name,
            "image": f"ghcr.io/owner/operion-{service_name}@sha256:{'b' * 64}",
        }
        record.update(changes)
        (self.directory / f"image-{service_name}.json").write_text(json.dumps(record))

    def args(self, **changes):
        values = dict(
            manifest_dir=self.directory,
            repository=REPOSITORY,
            revision=REVISION,
            env_file=self.env_file,
            runtime_dir=self.runtime,
            check=False,
        )
        values.update(changes)
        return SimpleNamespace(**values)

    def test_wrong_revisions_services_registries_mutable_tags_and_extra_fields_are_rejected(
        self,
    ):
        for changes in (
            {"revision": "c" * 40},
            {"service": "web"},
            {"image": "ghcr.io/owner/operion-agent:latest"},
            {"image": f"ghcr.io/other/operion-agent@sha256:{'b' * 64}"},
            {"image": f"example.com/owner/operion-agent@sha256:{'b' * 64}"},
            {"extra": "not allowed"},
        ):
            with (
                self.subTest(changes=changes),
                patch.object(release.subprocess, "run") as run,
            ):
                self.record("agent", **changes)
                with self.assertRaises(ValueError):
                    release.deploy(self.args())
                run.assert_not_called()

    def test_mixed_or_missing_image_records_fail_before_deployment(self):
        (self.directory / "image-web.json").unlink()
        with patch.object(release.subprocess, "run") as run, self.assertRaises(OSError):
            release.deploy(self.args())
        run.assert_not_called()

    def test_checkout_and_host_configuration_must_match_before_running_docker(self):
        for changes, actual in (
            ({}, "c" * 40),
            ({"env_file": Path("relative.env")}, REVISION),
            ({"runtime_dir": Path("relative")}, REVISION),
            ({"runtime_dir": self.directory / "missing"}, REVISION),
        ):
            with (
                self.subTest(changes=changes),
                patch.object(release.subprocess, "check_output", return_value=actual),
                patch.object(release.subprocess, "run") as run,
            ):
                with self.assertRaises(ValueError):
                    release.deploy(self.args(**changes))
                run.assert_not_called()

    def test_only_digest_images_are_forwarded_to_the_observed_deployer(self):
        def inspect(command, *, cwd, env, check):
            override = json.loads(
                Path(env["OPERION_GATEWAY_IMAGE_OVERRIDE"]).read_text()
            )
            self.assertEqual({"agent", "web"}, set(override["services"]))
            for service, config in override["services"].items():
                self.assertEqual(
                    {"image": f"ghcr.io/owner/operion-{service}@sha256:{'b' * 64}"},
                    config,
                )
            self.assertEqual(REVISION, env["OPERION_RELEASE_ID"])
            self.assertEqual(str(self.runtime), env["OPERION_GATEWAY_RUNTIME_DIR"])
            self.assertEqual(str(self.env_file), env["OPERION_GATEWAY_ENV_FILE"])
            self.assertEqual("--check", command[-1])
            self.assertTrue(check)

        with (
            patch.object(release.subprocess, "check_output", return_value=REVISION),
            patch.object(release.subprocess, "run", side_effect=inspect) as run,
        ):
            release.deploy(self.args(check=True))
        run.assert_called_once()


class ObservedDeploymentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.log = self.directory / "calls.jsonl"
        self.env_file = self.directory / "telemetry.env"
        self.env_file.write_text("OPERION_OTEL_ENABLED=1\n")
        docker = self.directory / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            + """
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["CALL_LOG"]).open("a") as out:
    out.write(json.dumps(args) + "\\n")
if args[0] == "compose":
    if "config" in args:
        env = {"OPERION_OTEL_ENABLED": os.environ.get("TRACING", "1"),
               "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": os.environ.get("OTLP_ENDPOINT", "http://collector:4318/v1/traces")}
        print(json.dumps({"services": {s: {"environment": env} for s in ("agent", "web")}}))
    elif "ps" in args:
        print(args[-1])
elif args[0] == "inspect":
    if "State.Running" in args[2]:
        print(os.environ.get("COLLECTOR", "true"))
    else:
        print("OPERION_OTEL_ENABLED=1")
"""
        )
        docker.chmod(0o700)

    def execute(self, *args, **changes):
        environment = dict(
            os.environ,
            PATH=f"{self.directory}{os.pathsep}{os.environ['PATH']}",
            OPERION_GATEWAY_ENV_FILE=str(self.env_file),
            OPERION_GATEWAY_IMAGE_OVERRIDE=str(self.directory / "images.json"),
            CALL_LOG=str(self.log),
        )
        environment.update(changes)
        result = subprocess.run(
            ["bash", "scripts/deploy_gateway_observed.sh", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    def test_disabled_tracing_or_stopped_collector_blocks_all_mutations(self):
        for changes in (
            {"TRACING": "0"},
            {"COLLECTOR": "false"},
            {"OTLP_ENDPOINT": "http://other:4318/v1/traces"},
        ):
            with self.subTest(changes=changes):
                result, calls = self.execute(**changes)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(
                    any(
                        verb in call
                        for call in calls
                        for verb in ("pull", "build", "up")
                    )
                )

    def test_check_is_read_only_and_release_pull_does_not_rebuild_or_restart_dependencies(
        self,
    ):
        result, calls = self.execute("--check")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(
            any(verb in call for call in calls for verb in ("pull", "build", "up"))
        )
        self.log.unlink()
        result, calls = self.execute()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any("pull" in call for call in calls))
        self.assertFalse(any("build" in call for call in calls))
        up = next(call for call in calls if "up" in call)
        self.assertEqual(
            ["--no-deps", "--no-build", "--pull", "never", "--wait", "agent", "web"],
            up[up.index("-d") + 1 :],
        )

    def test_existing_source_build_path_remains_available(self):
        result, calls = self.execute("agent", OPERION_GATEWAY_IMAGE_OVERRIDE="")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any(call[-2:] == ["build", "agent"] for call in calls))
        self.assertFalse(any("pull" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
