from __future__ import annotations

import csv
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

IDENTITY_FIELDS = [
    "entity_type",
    "source_system",
    "source_id",
    "canonical_id",
    "target_system",
    "target_id",
    "batch_id",
    "mapping_version",
    "load_status",
    "error",
]

ERPNEXT_READBACKS = (
    ("Customer", "custom_operion_source_key", "organization"),
    ("Supplier", "custom_operion_sourcekey", "organization"),
    ("Item", "custom_operion_source_key", "product"),
    ("Contact", "custom_operion_source_key", "contact"),
    ("Sales Order", "custom_operion_source_key", "sales_order"),
    ("Purchase Order", "custom_operion_source_key", "purchase_order"),
)

ERPNEXT_CHILD_READBACKS = (
    (
        "Sales Order",
        "items",
        "custom_operion_source_key_items",
        "sales_order_line",
    ),
    (
        "Purchase Order",
        "items",
        "custom_operion_source_key",
        "purchase_order_line",
    ),
)

ERPNEXT_PROTECTED_DOCTYPES = frozenset(
    {
        "Customer",
        "Supplier",
        "Item",
        "Sales Order",
        "Purchase Order",
        "Warehouse",
        "Bin",
        "UOM",
    }
)
ERPNEXT_DENIED_ACTIONS = frozenset(
    {"create", "update", "delete", "submit", "cancel", "amend"}
)
ERPNEXT_EVIDENCE_MAX_AGE = timedelta(hours=24)


class IdentityReadbackError(RuntimeError):
    pass


class JsonReadClient:
    """Small GET-only JSON client used by E1 identity reconciliation."""

    def __init__(
        self,
        base_url: str,
        authorization: str,
        timeout: float = 10,
        open_url: Callable[..., Any] | None = None,
    ) -> None:
        if not authorization:
            raise ValueError("authorization is required")
        self.base_url = base_url.rstrip("/")
        self.authorization = authorization
        self.timeout = timeout
        self._open_url = open_url or urllib.request.urlopen

    def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(params or {})
        url = self.base_url + path + (f"?{query}" if query else "")
        request = urllib.request.Request(
            url,
            headers={"Authorization": self.authorization, "Accept": "application/json"},
            method="GET",
        )
        try:
            with self._open_url(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            raise IdentityReadbackError(
                f"read request failed with HTTP {error.code} for {path}"
            ) from error
        except urllib.error.URLError as error:
            raise IdentityReadbackError(
                f"read request failed for {path}: {error.reason}"
            ) from error
        if not isinstance(payload, dict):
            raise IdentityReadbackError(
                f"read request returned non-object JSON for {path}"
            )
        return payload


class TwentyReadClient:
    def __init__(self, base_url: str, api_key: str, **kwargs: Any) -> None:
        if not api_key:
            raise ValueError("TWENTY_API_KEY_READ_ONLY is required")
        self.http = JsonReadClient(base_url, f"Bearer {api_key}", **kwargs)

    def records(self, resource: str, page_size: int = 100) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {"limit": page_size}
            if cursor:
                params["starting_after"] = cursor
            payload = self.http.get_json(f"/rest/{resource}", params)
            data = payload.get("data", {})
            page = data if isinstance(data, list) else data.get(resource, [])
            if not isinstance(page, list):
                raise IdentityReadbackError(
                    f"Twenty {resource} payload has an invalid data shape"
                )
            records.extend(item for item in page if isinstance(item, dict))
            page_info = payload.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                return records
            next_cursor = str(page_info.get("endCursor") or "")
            if not next_cursor or next_cursor == cursor:
                raise IdentityReadbackError(
                    f"Twenty {resource} pagination cursor did not advance"
                )
            cursor = next_cursor


class ERPNextReadClient:
    def __init__(self, base_url: str, token: str, **kwargs: Any) -> None:
        if ":" not in token:
            raise ValueError("ERPNext token must use api_key:api_secret format")
        self.http = JsonReadClient(base_url, f"token {token}", **kwargs)

    def records(
        self,
        doctype: str,
        fields: list[str],
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        start = 0
        path = "/api/resource/" + urllib.parse.quote(doctype, safe="")
        while True:
            payload = self.http.get_json(
                path,
                {
                    "fields": json.dumps(fields, separators=(",", ":")),
                    "limit_start": start,
                    "limit_page_length": page_size,
                    "order_by": "name asc",
                },
            )
            page = payload.get("data", [])
            if not isinstance(page, list):
                raise IdentityReadbackError(
                    f"ERPNext {doctype} payload has an invalid data shape"
                )
            records.extend(item for item in page if isinstance(item, dict))
            if len(page) < page_size:
                return records
            start += len(page)

    def record(self, doctype: str, name: str) -> dict[str, Any]:
        path = "/api/resource/{}/{}".format(
            urllib.parse.quote(doctype, safe=""),
            urllib.parse.quote(name, safe=""),
        )
        payload = self.http.get_json(path)
        record = payload.get("data")
        if not isinstance(record, dict):
            raise IdentityReadbackError(
                f"ERPNext {doctype} detail payload has an invalid data shape"
            )
        return record


def collect_twenty_readbacks(client: TwentyReadClient) -> list[dict[str, str]]:
    readbacks: list[dict[str, str]] = []
    for resource, entity_type in (("companies", "organization"), ("people", "contact")):
        for record in client.records(resource):
            canonical_id = str(record.get("wwiExternalId") or "")
            target_id = str(record.get("id") or "")
            if canonical_id.startswith("wwi:") and target_id:
                readbacks.append(
                    {
                        "target_system": "twenty",
                        "entity_type": entity_type,
                        "canonical_id": canonical_id,
                        "target_id": target_id,
                    }
                )
    return readbacks


def collect_erpnext_readbacks(client: ERPNextReadClient) -> list[dict[str, str]]:
    readbacks: list[dict[str, str]] = []
    parent_records: dict[str, list[dict[str, Any]]] = {}
    for doctype, source_field, entity_type in ERPNEXT_READBACKS:
        records = client.records(doctype, ["name", source_field])
        parent_records[doctype] = records
        for record in records:
            canonical_id = str(record.get(source_field) or "")
            target_id = str(record.get("name") or "")
            if canonical_id.startswith("wwi:") and target_id:
                readbacks.append(
                    {
                        "target_system": "erpnext",
                        "entity_type": entity_type,
                        "canonical_id": canonical_id,
                        "target_id": target_id,
                    }
                )
    for doctype, table_field, source_field, entity_type in ERPNEXT_CHILD_READBACKS:
        for parent in parent_records[doctype]:
            detail = client.record(doctype, str(parent["name"]))
            children = detail.get(table_field, [])
            if not isinstance(children, list):
                raise IdentityReadbackError(
                    f"ERPNext {doctype}.{table_field} has an invalid data shape"
                )
            for child in children:
                canonical_id = str(child.get(source_field) or "")
                target_id = str(child.get("name") or "")
                if canonical_id.startswith("wwi:") and target_id:
                    readbacks.append(
                        {
                            "target_system": "erpnext",
                            "entity_type": entity_type,
                            "canonical_id": canonical_id,
                            "target_id": target_id,
                        }
                    )
    return readbacks


def read_identity_map(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != IDENTITY_FIELDS:
            raise IdentityReadbackError(
                "identity map headers do not match the v1 contract: "
                f"{reader.fieldnames}"
            )
        return list(reader)


def reconcile_identity_rows(
    rows: list[dict[str, str]],
    readbacks: list[dict[str, str]],
    target_systems: set[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    def expects_target(row: dict[str, str]) -> bool:
        return (
            row["target_system"] in target_systems
            and row["load_status"] != "not_applicable"
        )

    expected_keys = {
        (row["target_system"], row["canonical_id"])
        for row in rows
        if expects_target(row)
    }
    if len(expected_keys) != sum(expects_target(row) for row in rows):
        raise IdentityReadbackError(
            "identity map contains duplicate target/canonical rows"
        )

    readback_keys = [(row["target_system"], row["canonical_id"]) for row in readbacks]
    duplicate_keys = sorted(
        key for key, count in Counter(readback_keys).items() if count > 1
    )
    target_ids = [(row["target_system"], row["target_id"]) for row in readbacks]
    duplicate_target_ids = sorted(
        key for key, count in Counter(target_ids).items() if count > 1
    )
    if duplicate_keys or duplicate_target_ids:
        raise IdentityReadbackError(
            f"readback is ambiguous; duplicate_keys={duplicate_keys}, "
            f"duplicate_target_ids={duplicate_target_ids}"
        )

    index = {
        (row["target_system"], row["canonical_id"]): row
        for row in readbacks
        if row["target_system"] in target_systems
    }
    output: list[dict[str, str]] = []
    metrics = {
        system: {"expected": 0, "matched": 0, "missing": 0, "unexpected": 0}
        for system in sorted(target_systems)
    }
    missing: list[dict[str, str]] = []
    for original in rows:
        row = dict(original)
        system = row["target_system"]
        if not expects_target(row):
            output.append(row)
            continue
        metrics[system]["expected"] += 1
        match = index.get((system, row["canonical_id"]))
        if match is None:
            row["target_id"] = ""
            row["load_status"] = "missing"
            row["error"] = "target readback missing"
            metrics[system]["missing"] += 1
            missing.append(
                {
                    "target_system": system,
                    "entity_type": row["entity_type"],
                    "canonical_id": row["canonical_id"],
                }
            )
        else:
            if match["entity_type"] != row["entity_type"]:
                raise IdentityReadbackError(
                    f"entity type mismatch for {system}:{row['canonical_id']}"
                )
            row["target_id"] = match["target_id"]
            row["load_status"] = "loaded"
            row["error"] = ""
            metrics[system]["matched"] += 1
        output.append(row)

    for system, _canonical_id in set(index) - expected_keys:
        metrics[system]["unexpected"] += 1

    report = {
        "status": "passed" if not missing else "failed",
        "target_systems": sorted(target_systems),
        "metrics": metrics,
        "missing": missing,
    }
    return output, report


def write_identity_map(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=IDENTITY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def verify_erpnext_permission_evidence(path: Path, token: str) -> None:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    scope = evidence.get("scope", {})
    protected = set(scope.get("protected_doctypes", []))
    checks = evidence.get("checks", {})
    fingerprint = hashlib.sha256(token.split(":", 1)[0].encode()).hexdigest()
    try:
        observed_at = datetime.fromisoformat(
            str(evidence["observed_at"]).replace("Z", "+00:00")
        )
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        evidence_age = datetime.now(UTC) - observed_at
        evidence_is_fresh = (
            -timedelta(minutes=5) <= evidence_age <= ERPNEXT_EVIDENCE_MAX_AGE
        )
    except (KeyError, TypeError, ValueError):
        evidence_is_fresh = False
    protected_checks_are_read_only = all(
        isinstance(checks.get(doctype), dict)
        and checks[doctype].get("read") == "allowed"
        and all(
            checks[doctype].get(action) == "denied" for action in ERPNEXT_DENIED_ACTIONS
        )
        for doctype in ERPNEXT_PROTECTED_DOCTYPES
    )
    if (
        evidence.get("evidence_version") != "erpnext-critical-readonly-v1"
        or not evidence_is_fresh
        or evidence.get("target_system") != "erpnext"
        or evidence.get("status") != "passed"
        or evidence.get("api_key_fingerprint") != fingerprint
        or protected != ERPNEXT_PROTECTED_DOCTYPES
        or not protected_checks_are_read_only
    ):
        raise IdentityReadbackError(
            "ERPNext permission evidence is missing, stale, or does not prove the "
            "protected business DocTypes are read-only"
        )
