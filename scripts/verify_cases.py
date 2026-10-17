"""Reproducible local case reports. No real model, live ERP or browser implied."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def worker(test, output):
    sys.path.insert(0, str(ROOT / "tests"))
    suite = unittest.defaultTestLoader.loadTestsFromName(test)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    write_json(
        output,
        {
            "tests": result.testsRun,
            "failures": [str(t) for t, _ in result.failures],
            "errors": [str(t) for t, _ in result.errors],
            "skipped": [(str(t), why) for t, why in result.skipped],
            "status": "FAIL"
            if not result.wasSuccessful() or not result.testsRun
            else "SKIP"
            if result.skipped
            else "PASS",
        },
    )
    return 0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?", default="all")
    parser.add_argument(
        "--layer", choices=["all", "domain", "agent", "mcp"], default="all"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports/developer")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ.pop("OPERION_TEST_ACTION_DATABASE_URL", None)
    os.environ["OPERION_OTEL_ENABLED"] = "0"
    os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
    os.environ["PYTHONPATH"] = str(ROOT / "src")
    if args.worker:
        return worker(args.worker, args.output)
    catalog = json.loads((ROOT / "evaluations/developer/cases.json").read_text())
    chosen = [
        (case, layer, test, definition["expected"])
        for case, definition in catalog["cases"].items()
        if args.case in ("all", case)
        for layer, test in definition["layers"].items()
        if args.layer in ("all", layer)
    ]
    if not chosen:
        parser.error("no cases match; unsupported layers must not count as success")
    directory = args.output.resolve() / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    )
    directory.mkdir(parents=True, exist_ok=False)

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    files = [
        p
        for base in ("src", "tests", "evaluations/developer", "scripts")
        for p in (ROOT / base).rglob("*")
        if p.is_file() and p.suffix in (".py", ".json", ".csv", ".sh")
    ]
    manifest = {
        "schema": catalog["version"],
        "started_at": datetime.now(UTC).isoformat(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "tracked_diff_sha256": digest(subprocess.check_output(["git", "diff", "HEAD"])),
        "files": {
            str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(files)
        },
        "lock_sha256": digest((ROOT / "uv.lock").read_bytes()),
        "python": sys.version,
        "data_mode": "fixture",
        "model": "FunctionModel (scripted)",
        "live_services": False,
        "browser": False,
        "status": "RUNNING",
        "results": [],
    }
    write_json(directory / "manifest.json", manifest)
    for case, layer, test, expected in chosen:
        stem = f"{case}-{layer}"
        result_path = directory / f"{stem}.json"
        log_path = directory / f"{stem}.log"
        row = {
            "case": case,
            "layer": layer,
            "test": test,
            "expected": expected,
            "status": "RUNNING",
            "log": log_path.name,
            "rerun": f"scripts/verify.sh case {case} --layer {layer}",
        }
        manifest["results"].append(row)
        write_json(directory / "manifest.json", manifest)
        try:
            with log_path.open("w") as log:
                process = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        test,
                        "--output",
                        str(result_path),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=90,
                )
            if result_path.exists():
                row.update(json.loads(result_path.read_text()))
                if process.returncode and row["status"] == "PASS":
                    row["status"] = "FAIL"
            else:
                row.update(status="BLOCKED", detail="worker exited without result")
        except subprocess.TimeoutExpired:
            row.update(
                status="BLOCKED", detail="case exceeded 90 seconds; see partial log"
            )
        write_json(directory / "manifest.json", manifest)
        print(f"{case}/{layer}: {row['status']}", flush=True)
    passed = all(r["status"] == "PASS" for r in manifest["results"])
    manifest.update(
        status="PASS" if passed else "FAIL", finished_at=datetime.now(UTC).isoformat()
    )
    write_json(directory / "manifest.json", manifest)
    suite = ET.Element(
        "testsuite",
        name="developer",
        tests=str(len(chosen)),
        failures=str(sum(r["status"] != "PASS" for r in manifest["results"])),
    )
    rows = []
    for row in manifest["results"]:
        test = ET.SubElement(
            suite, "testcase", name=row["case"], classname=row["layer"]
        )
        if row["status"] != "PASS":
            ET.SubElement(test, "failure", message=row["status"]).text = row.get(
                "detail", row["log"]
            )
        rows.append(
            "<tr>"
            + "".join(
                "<td>" + html.escape(str(row[k])) + "</td>"
                for k in ("case", "layer", "status", "expected", "rerun")
            )
            + f'<td><a href="{html.escape(row["log"], quote=True)}">Assertions/log</a></td></tr>'
        )
    ET.ElementTree(suite).write(
        directory / "junit.xml", encoding="utf-8", xml_declaration=True
    )
    (directory / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Operion verification</title>'
        "<h1>Developer evidence</h1><p>Tracked fixtures; scripted models; real stdio MCP. No live ERP or browser.</p>"
        '<table border="1"><tr><th>Case</th><th>Layer</th><th>Actual</th><th>Expected</th><th>Rerun</th><th>Evidence</th></tr>'
        + "".join(rows)
        + "</table>"
    )
    print(f"Evidence: {directory}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
