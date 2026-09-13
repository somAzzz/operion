from __future__ import annotations

import argparse
from pathlib import Path

from .download import download_wwi
from .pipeline import run_etl
from .preimport import validate_files
from .twenty import load_companies


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="operion-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)
    download = subparsers.add_parser("download-wwi", help="Download an immutable WWI snapshot")
    download.add_argument("--raw-root", type=Path, default=Path("data/raw/wwi"))
    download.add_argument("--snapshot-id")
    etl = subparsers.add_parser("run", help="Extract, validate, map, and export a WWI sample batch")
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
    load = subparsers.add_parser(
        "load-twenty-companies", help="Load Companies and persist Twenty UUID readback"
    )
    load.add_argument("--companies", type=Path, required=True)
    load.add_argument("--people", type=Path, required=True)
    load.add_argument("--identity-map", type=Path, required=True)
    load.add_argument("--readback", type=Path, required=True)
    load.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "download-wwi":
        print(download_wwi(args.raw_root, args.snapshot_id))
    elif args.command == "run":
        print(run_etl(args.snapshot, args.batch_id, args.data_root, args.reports_root, args.container, args.order_limit))
    elif args.command == "validate-twenty":
        result = validate_files(args.companies, args.people, args.report)
        print(result)
        if result["status"] != "passed":
            raise SystemExit(1)
    elif args.command == "load-twenty-companies":
        print(load_companies(
            args.companies, args.people, args.identity_map, args.readback, args.env_file
        ))
