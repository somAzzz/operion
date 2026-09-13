from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


COMPANY_EXTERNAL_ID = "WWI External ID"
COMPANY_DOMAIN = "Domain Name / Link URL"
PERSON_COMPANY_EXTERNAL_ID = "Company WWI External ID"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def normalize_domain(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host = (parsed.hostname or "").lower().removeprefix("www.").rstrip(".")
    return host.encode("idna").decode("ascii") if host else ""


def validate_twenty_imports(
    company_rows: list[dict[str, str]],
    people_rows: list[dict[str, str]],
) -> dict:
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    def issue(kind: str, row: int, field: str, message: str) -> None:
        errors.append({"entity": kind, "row": row, "field": field, "message": message})

    company_ids = [row.get(COMPANY_EXTERNAL_ID, "").strip() for row in company_rows]
    duplicate_company_ids = {
        value for value, count in Counter(company_ids).items() if value and count > 1
    }
    domains = [normalize_domain(row.get(COMPANY_DOMAIN, "")) for row in company_rows]
    duplicate_domains = {
        value for value, count in Counter(domains).items() if value and count > 1
    }
    for index, (row, external_id, domain) in enumerate(
        zip(company_rows, company_ids, domains, strict=True), start=2
    ):
        if not row.get("Name", "").strip():
            issue("company", index, "Name", "company name is required")
        if not external_id:
            issue("company", index, COMPANY_EXTERNAL_ID, "unique source ID is required")
        elif external_id in duplicate_company_ids:
            issue("company", index, COMPANY_EXTERNAL_ID, "duplicate unique source ID")
        raw_domain = row.get(COMPANY_DOMAIN, "").strip()
        if raw_domain and not domain:
            issue("company", index, COMPANY_DOMAIN, "domain cannot be normalized")
        elif domain in duplicate_domains:
            issue("company", index, COMPANY_DOMAIN, "duplicate normalized domain")
        elif raw_domain and raw_domain != f"https://{domain}":
            issue(
                "company", index, COMPANY_DOMAIN,
                f"domain must be canonicalized as https://{domain}",
            )
        if row.get("Id", "").strip():
            issue(
                "company", index, "Id",
                "leave target Id blank; WWI External ID is the only import identity",
            )

    valid_company_ids = {value for value in company_ids if value}
    people_ids = [row.get(COMPANY_EXTERNAL_ID, "").strip() for row in people_rows]
    duplicate_people_ids = {
        value for value, count in Counter(people_ids).items() if value and count > 1
    }
    for index, (row, external_id) in enumerate(zip(people_rows, people_ids, strict=True), start=2):
        if not row.get("First Name", "").strip():
            issue("person", index, "First Name", "person first name is required")
        if not external_id:
            issue("person", index, COMPANY_EXTERNAL_ID, "unique source ID is required")
        elif external_id in duplicate_people_ids:
            issue("person", index, COMPANY_EXTERNAL_ID, "duplicate unique source ID")
        relation = row.get(PERSON_COMPANY_EXTERNAL_ID, "").strip()
        if relation and relation not in valid_company_ids:
            issue(
                "person", index, PERSON_COMPANY_EXTERNAL_ID,
                "relation does not resolve to a Company WWI External ID",
            )
        if not relation:
            warnings.append({
                "entity": "person", "row": index,
                "field": PERSON_COMPANY_EXTERNAL_ID,
                "message": "no source company relation; leave Company blank",
            })

    return {
        "status": "passed" if not errors else "failed",
        "company_rows": len(company_rows),
        "people_rows": len(people_rows),
        "errors": errors,
        "warnings": warnings,
    }


def validate_files(companies: Path, people: Path, report: Path | None = None) -> dict:
    result = validate_twenty_imports(read_csv(companies), read_csv(people))
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
