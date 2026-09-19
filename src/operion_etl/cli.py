from __future__ import annotations

import argparse
import json
from pathlib import Path

from .download import download_wwi
from .erpnext_audit import audit_erpnext
from .erpnext_preimport import validate_directory
from .identity_readback import (
    ERPNextReadClient,
    TwentyReadClient,
    collect_erpnext_readbacks,
    collect_twenty_readbacks,
    read_identity_map,
    reconcile_identity_rows,
    verify_erpnext_permission_evidence,
    write_identity_map,
)
from .pipeline import run_etl
from .preimport import validate_files
from .twenty import load_companies, read_env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="operion-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)
    download = subparsers.add_parser(
        "download-wwi", help="Download an immutable WWI snapshot"
    )
    download.add_argument("--raw-root", type=Path, default=Path("data/raw/wwi"))
    download.add_argument("--snapshot-id")
    etl = subparsers.add_parser(
        "run", help="Extract, validate, map, and export a WWI sample batch"
    )
    etl.add_argument("--snapshot", type=Path, required=True)
    etl.add_argument("--batch-id", required=True)
    etl.add_argument("--data-root", type=Path, default=Path("data"))
    etl.add_argument("--reports-root", type=Path, default=Path("reports"))
    etl.add_argument("--container", default="enterprise-demo-mssql")
    etl.add_argument("--order-limit", type=int, default=8)
    validate = subparsers.add_parser(
        "validate-twenty", help="Validate Twenty Company and People CSVs before import"
    )
    validate.add_argument("--companies", type=Path, required=True)
    validate.add_argument("--people", type=Path, required=True)
    validate.add_argument("--report", type=Path)
    validate_erpnext = subparsers.add_parser(
        "validate-erpnext", help="Validate an ERPNext CSV directory before import"
    )
    validate_erpnext.add_argument("--directory", type=Path, required=True)
    validate_erpnext.add_argument("--report", type=Path)
    audit = subparsers.add_parser(
        "audit-erpnext",
        help="Read back ERPNext through the Frappe API and reconcile a CSV batch",
    )
    audit.add_argument("--directory", type=Path, required=True)
    audit.add_argument("--report", type=Path)
    audit.add_argument("--site", default="erp.localhost")
    audit.add_argument("--backend-container", default="erpnext-backend-1")
    load = subparsers.add_parser(
        "load-twenty-companies", help="Load Companies and persist Twenty UUID readback"
    )
    load.add_argument("--companies", type=Path, required=True)
    load.add_argument("--people", type=Path, required=True)
    load.add_argument("--identity-map", type=Path, required=True)
    load.add_argument("--readback", type=Path, required=True)
    load.add_argument("--env-file", type=Path, default=Path(".env"))
    reconcile = subparsers.add_parser(
        "reconcile-identities",
        help="Read target IDs through GET-only clients and reconcile an identity map",
    )
    reconcile.add_argument("--identity-map", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    reconcile.add_argument("--report", type=Path, required=True)
    reconcile.add_argument(
        "--target", action="append", choices=("twenty", "erpnext"), required=True
    )
    reconcile.add_argument("--env-file", type=Path, default=Path(".env"))
    reconcile.add_argument("--erpnext-permission-evidence", type=Path)
    return parser


def reconcile_identities(args: argparse.Namespace) -> dict:
    values = read_env(args.env_file)
    targets = set(args.target)
    readbacks = []
    if "twenty" in targets:
        client = TwentyReadClient(
            values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
            values.get("TWENTY_API_KEY_READ_ONLY", ""),
        )
        readbacks.extend(collect_twenty_readbacks(client))
    if "erpnext" in targets:
        token = values.get("ERPNEXT_API_KEY_READ_ONLY", "")
        if args.erpnext_permission_evidence is None:
            raise SystemExit("--erpnext-permission-evidence is required for ERPNext")
        verify_erpnext_permission_evidence(args.erpnext_permission_evidence, token)
        client = ERPNextReadClient(
            values.get("ERPNEXT_API_BASE_URL", "http://localhost:8080"), token
        )
        readbacks.extend(collect_erpnext_readbacks(client))
    rows, result = reconcile_identity_rows(
        read_identity_map(args.identity_map), readbacks, targets
    )
    write_identity_map(args.output, rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "download-wwi":
        print(download_wwi(args.raw_root, args.snapshot_id))
    elif args.command == "run":
        print(
            run_etl(
                args.snapshot,
                args.batch_id,
                args.data_root,
                args.reports_root,
                args.container,
                args.order_limit,
            )
        )
    elif args.command == "validate-twenty":
        result = validate_files(args.companies, args.people, args.report)
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
    elif args.command == "validate-erpnext":
        result = validate_directory(args.directory, args.report)
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
    elif args.command == "audit-erpnext":
        result = audit_erpnext(
            args.directory, args.backend_container, args.site, args.report
        )
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
    elif args.command == "load-twenty-companies":
        print(
            load_companies(
                args.companies,
                args.people,
                args.identity_map,
                args.readback,
                args.env_file,
            )
        )
    elif args.command == "reconcile-identities":
        result = reconcile_identities(args)
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
