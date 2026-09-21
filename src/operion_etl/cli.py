from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from .download import download_wwi
from .e2_data import prepare_e2_batch, seed_e2_targets
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
from .interview_demo import (
    DEFAULT_BUSINESS_DATE,
    DEFAULT_SEED,
    apply_interview_demo,
    prepare_interview_demo,
    provision_plan,
    validate_interview_demo,
)
from .interview_wwi import (
    DEFAULT_BUSINESS_DATE as WWI_BUSINESS_DATE,
)
from .interview_wwi import (
    DEFAULT_SEED as WWI_SEED,
)
from .interview_wwi import (
    DEFAULT_SOURCE_MANIFEST,
    apply_interview_wwi,
    prepare_interview_wwi,
    provision_wwi_plan,
    validate_interview_wwi,
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
    prepare_e2 = subparsers.add_parser(
        "prepare-e2-data",
        help="Build a deterministic E2 evaluation batch from the accepted E1 batch",
    )
    prepare_e2.add_argument("--base-directory", type=Path, required=True)
    prepare_e2.add_argument("--base-identity-map", type=Path, required=True)
    prepare_e2.add_argument("--output-directory", type=Path, required=True)
    prepare_e2.add_argument("--output-identity-map", type=Path, required=True)
    seed_e2 = subparsers.add_parser(
        "seed-e2-targets",
        help="Idempotently load the prepared E2 fixtures into target systems",
    )
    seed_e2.add_argument("--identity-map", type=Path, required=True)
    seed_e2.add_argument("--report", type=Path, required=True)
    seed_e2.add_argument("--env-file", type=Path, default=Path(".env"))
    prepare_demo = subparsers.add_parser(
        "prepare-interview-demo",
        help="Generate the deterministic, isolated interview-demo-v1 dataset",
    )
    prepare_demo.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/canonical/interview-demo-v1"),
    )
    prepare_demo.add_argument(
        "--identity-map",
        type=Path,
        default=Path("reports/interview-demo-v1/identity_map.csv"),
    )
    prepare_demo.add_argument(
        "--business-date", type=date.fromisoformat, default=DEFAULT_BUSINESS_DATE
    )
    prepare_demo.add_argument("--seed", type=int, default=DEFAULT_SEED)
    validate_demo = subparsers.add_parser(
        "validate-interview-demo",
        help="Validate counts, references, edge cases, and amounts in interview-demo-v1",
    )
    validate_demo.add_argument(
        "--directory", type=Path, default=Path("data/canonical/interview-demo-v1")
    )
    provision_demo = subparsers.add_parser(
        "provision-interview-demo",
        help="Print a dry-run plan by default; --apply performs guarded idempotent writes",
    )
    provision_demo.add_argument(
        "--directory", type=Path, default=Path("data/canonical/interview-demo-v1")
    )
    provision_demo.add_argument(
        "--identity-map",
        type=Path,
        default=Path("reports/interview-demo-v1/identity_map.csv"),
    )
    provision_demo.add_argument("--apply", action="store_true")
    provision_demo.add_argument(
        "--admin-env",
        type=Path,
        help="Dedicated provisioning credentials; required with --apply",
    )
    prepare_wwi = subparsers.add_parser(
        "prepare-interview-wwi",
        help="Extract the deterministic interview-wwi-v1 batch from pinned WWI v1",
    )
    prepare_wwi.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/canonical/interview-wwi-v1"),
    )
    prepare_wwi.add_argument(
        "--identity-map",
        type=Path,
        default=Path("reports/interview-wwi-v1/identity_map.csv"),
    )
    prepare_wwi.add_argument(
        "--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST
    )
    prepare_wwi.add_argument("--container", default="enterprise-demo-mssql")
    prepare_wwi.add_argument(
        "--business-date", type=date.fromisoformat, default=WWI_BUSINESS_DATE
    )
    prepare_wwi.add_argument("--seed", type=int, default=WWI_SEED)
    validate_wwi = subparsers.add_parser(
        "validate-interview-wwi",
        help="Validate lineage, counts, references, edge cases, and WWI amounts",
    )
    validate_wwi.add_argument(
        "--directory", type=Path, default=Path("data/canonical/interview-wwi-v1")
    )
    provision_wwi = subparsers.add_parser(
        "provision-interview-wwi",
        help="Dry-run WWI provisioning; --apply uses the same guarded writer",
    )
    provision_wwi.add_argument(
        "--directory", type=Path, default=Path("data/canonical/interview-wwi-v1")
    )
    provision_wwi.add_argument(
        "--identity-map",
        type=Path,
        default=Path("reports/interview-wwi-v1/identity_map.csv"),
    )
    provision_wwi.add_argument("--apply", action="store_true")
    provision_wwi.add_argument(
        "--admin-env",
        type=Path,
        help="Dedicated provisioning credentials; required with --apply",
    )
    return parser


def reconcile_identities(args: argparse.Namespace) -> dict:
    values = read_env(args.env_file)
    targets = set(args.target)
    readbacks = []
    source_observed_at: dict[str, str] = {}
    if "twenty" in targets:
        client = TwentyReadClient(
            values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
            values.get("TWENTY_API_KEY_READ_ONLY", ""),
        )
        readbacks.extend(collect_twenty_readbacks(client))
        source_observed_at["twenty"] = datetime.now(UTC).isoformat()
    if "erpnext" in targets:
        token = values.get("ERPNEXT_API_KEY_READ_ONLY", "")
        if args.erpnext_permission_evidence is None:
            raise SystemExit("--erpnext-permission-evidence is required for ERPNext")
        verify_erpnext_permission_evidence(args.erpnext_permission_evidence, token)
        client = ERPNextReadClient(
            values.get("ERPNEXT_API_BASE_URL", "http://localhost:8080"), token
        )
        readbacks.extend(collect_erpnext_readbacks(client))
        source_observed_at["erpnext"] = datetime.now(UTC).isoformat()
    rows, result = reconcile_identity_rows(
        read_identity_map(args.identity_map), readbacks, targets
    )
    result["source_observed_at"] = source_observed_at
    if source_observed_at.keys() >= {"twenty", "erpnext"}:
        twenty_time = datetime.fromisoformat(source_observed_at["twenty"])
        erpnext_time = datetime.fromisoformat(source_observed_at["erpnext"])
        result["snapshot_skew_seconds"] = abs(
            (twenty_time - erpnext_time).total_seconds()
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
    elif args.command == "prepare-e2-data":
        print(
            prepare_e2_batch(
                args.base_directory,
                args.base_identity_map,
                args.output_directory,
                args.output_identity_map,
            )
        )
    elif args.command == "seed-e2-targets":
        print(seed_e2_targets(args.identity_map, args.report, args.env_file))
    elif args.command == "prepare-interview-demo":
        print(
            prepare_interview_demo(
                args.output_directory,
                args.identity_map,
                business_date=args.business_date,
                seed=args.seed,
            )
        )
    elif args.command == "validate-interview-demo":
        result = validate_interview_demo(args.directory)
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
    elif args.command == "provision-interview-demo":
        if args.apply:
            if args.admin_env is None:
                raise SystemExit("--admin-env is required with --apply")
            print(
                apply_interview_demo(args.directory, args.identity_map, args.admin_env)
            )
        else:
            print(provision_plan(args.directory))
    elif args.command == "prepare-interview-wwi":
        print(
            prepare_interview_wwi(
                args.output_directory,
                args.identity_map,
                source_manifest=args.source_manifest,
                container=args.container,
                business_date=args.business_date,
                seed=args.seed,
            )
        )
    elif args.command == "validate-interview-wwi":
        result = validate_interview_wwi(args.directory)
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
    elif args.command == "provision-interview-wwi":
        if args.apply:
            if args.admin_env is None:
                raise SystemExit("--admin-env is required with --apply")
            print(
                apply_interview_wwi(args.directory, args.identity_map, args.admin_env)
            )
        else:
            print(provision_wwi_plan(args.directory))
