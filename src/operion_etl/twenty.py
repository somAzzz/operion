from __future__ import annotations

import csv
import json
import urllib.error
import urllib.request
from pathlib import Path

from .preimport import COMPANY_EXTERNAL_ID, normalize_domain, validate_files


def read_env(path: Path = Path(".env")) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class TwentyClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        if not api_key:
            raise ValueError("TWENTY_API_KEY is missing")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> TwentyClient:
        values = read_env(env_file)
        return cls(
            values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
            values.get("TWENTY_API_KEY", ""),
        )

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers
        )
        try:
            with urllib.request.urlopen(request) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Twenty API {error.code} for {path}: {detail}"
            ) from error
        return result

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        result = self._request(
            "/graphql", {"query": query, "variables": variables or {}}
        )
        if result.get("errors"):
            raise RuntimeError(f"Twenty GraphQL error: {result['errors']}")
        return result["data"]

    def companies(self) -> list[dict]:
        payload = self._request("/rest/companies?limit=60")
        data = payload.get("data", [])
        if isinstance(data, dict):
            data = data.get("companies", [])
        return data

    def create_company(self, data: dict) -> dict:
        query = """
mutation CreateCompany($data: CompanyCreateInput!) {
  createCompany(data: $data) {
    id name wwiExternalId domainName { primaryLinkUrl }
  }
}
"""
        return self.graphql(query, {"data": data})["createCompany"]

    def update_company(self, record_id: str, data: dict) -> dict:
        query = """
mutation UpdateCompany($id: UUID!, $data: CompanyUpdateInput!) {
  updateCompany(id: $id, data: $data) {
    id name wwiExternalId domainName { primaryLinkUrl }
  }
}
"""
        return self.graphql(query, {"id": record_id, "data": data})["updateCompany"]


def _company_payload(row: dict[str, str]) -> dict:
    return {
        "name": row["Name"].strip(),
        "wwiExternalId": row[COMPANY_EXTERNAL_ID].strip(),
        "domainName": {
            "primaryLinkUrl": row.get("Domain Name / Link URL", "").strip(),
            "primaryLinkLabel": row.get("Domain Name / Link Label", "").strip(),
            "secondaryLinks": [],
        },
        "address": {
            "addressStreet1": row.get("Address / Address 1", "").strip(),
            "addressStreet2": row.get("Address / Address 2", "").strip(),
            "addressCity": row.get("Address / City", "").strip(),
            "addressPostcode": row.get("Address / Post Code", "").strip(),
            "addressState": row.get("Address / State", "").strip(),
            "addressCountry": row.get("Address / Country", "").strip(),
        },
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _update_identity_map(path: Path, companies: list[dict]) -> None:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    by_external_id = {row.get("wwiExternalId", ""): row["id"] for row in companies}
    for row in rows:
        if row["target_system"] != "twenty" or row["entity_type"] != "organization":
            continue
        target_id = by_external_id.get(row["canonical_id"])
        if target_id:
            row["target_id"] = target_id
            row["load_status"] = "loaded"
            row["error"] = ""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _update_run_manifest(
    identity_map_path: Path, readback_path: Path, result: dict
) -> None:
    manifest_path = identity_map_path.parent / "run_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["load_status"] = "twenty_companies_loaded_people_pending"
    manifest["twenty_company_load"] = {
        "status": result["status"],
        "created": result["created"],
        "updated": result["updated"],
        "readback_count": result["readback_count"],
        "readback": str(readback_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load_companies(
    companies_path: Path,
    people_path: Path,
    identity_map_path: Path,
    readback_path: Path,
    env_file: Path = Path(".env"),
) -> dict:
    validation = validate_files(companies_path, people_path)
    if validation["status"] != "passed":
        raise RuntimeError(f"Pre-import validation failed: {validation['errors']}")

    client = TwentyClient.from_env(env_file)
    rows = _read_csv(companies_path)
    existing = client.companies()
    by_external_id = {
        item.get("wwiExternalId"): item
        for item in existing
        if item.get("wwiExternalId")
    }
    by_name_and_domain = {}
    for item in existing:
        domain = normalize_domain(
            (item.get("domainName") or {}).get("primaryLinkUrl", "")
        )
        if domain:
            by_name_and_domain[(item.get("name", "").strip(), domain)] = item
    created = 0
    updated = 0
    for row in rows:
        payload = _company_payload(row)
        current = by_external_id.get(payload["wwiExternalId"])
        payload_domain = normalize_domain(payload["domainName"]["primaryLinkUrl"])
        if current is None and payload_domain:
            current = by_name_and_domain.get(
                (
                    payload["name"],
                    payload_domain,
                )
            )
        if current:
            client.update_company(current["id"], payload)
            updated += 1
        else:
            client.create_company(payload)
            created += 1

    readback = [
        {
            "id": row["id"],
            "name": row.get("name", ""),
            "wwiExternalId": row.get("wwiExternalId", ""),
            "domain": (row.get("domainName") or {}).get("primaryLinkUrl", ""),
        }
        for row in client.companies()
        if row.get("wwiExternalId", "").startswith("wwi:organization:")
    ]
    expected = {row[COMPANY_EXTERNAL_ID].strip() for row in rows}
    actual = {row["wwiExternalId"] for row in readback}
    if expected != actual:
        raise RuntimeError(
            f"Twenty readback mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    _update_identity_map(identity_map_path, readback)
    readback_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "passed",
        "created": created,
        "updated": updated,
        "readback_count": len(readback),
        "companies": sorted(readback, key=lambda row: row["wwiExternalId"]),
    }
    readback_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _update_run_manifest(identity_map_path, readback_path, result)
    return result
