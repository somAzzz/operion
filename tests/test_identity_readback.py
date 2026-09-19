import hashlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from operion_etl.identity_readback import (
    ERPNEXT_DENIED_ACTIONS,
    ERPNEXT_PROTECTED_DOCTYPES,
    ERPNextReadClient,
    IdentityReadbackError,
    TwentyReadClient,
    collect_erpnext_readbacks,
    collect_twenty_readbacks,
    is_canonical_id,
    reconcile_identity_rows,
    verify_erpnext_permission_evidence,
)
from operion_etl.pipeline import _identity_map


def identity_row(system: str, canonical_id: str, entity_type: str) -> dict[str, str]:
    return {
        "entity_type": entity_type,
        "source_system": "wwi",
        "source_id": canonical_id.rsplit(":", 1)[-1],
        "canonical_id": canonical_id,
        "target_system": system,
        "target_id": "",
        "batch_id": "batch",
        "mapping_version": "wwi-minimal-v1",
        "load_status": "pending",
        "error": "",
    }


class FakeResponse(io.StringIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class IdentityReadbackTests(unittest.TestCase):
    def test_supported_canonical_namespaces_include_e2_records(self):
        self.assertTrue(is_canonical_id("wwi:organization:customer:1"))
        self.assertTrue(is_canonical_id("operion:e2:organization:customer:a"))
        self.assertFalse(is_canonical_id("external:organization:customer:1"))

    def test_identity_map_excludes_orders_without_open_commitments(self):
        canonical = {
            "organizations": [],
            "contacts": [],
            "products": [],
            "sales_orders": [],
            "sales_order_lines": [],
            "purchase_orders": [
                {"canonical_id": "wwi:purchase_order:1", "source_id": "1"},
                {"canonical_id": "wwi:purchase_order:2", "source_id": "2"},
            ],
            "purchase_order_lines": [
                {
                    "canonical_id": "wwi:purchase_order_line:1",
                    "source_id": "1",
                    "purchase_order_canonical_id": "wwi:purchase_order:1",
                    "open_quantity": "0",
                },
                {
                    "canonical_id": "wwi:purchase_order_line:2",
                    "source_id": "2",
                    "purchase_order_canonical_id": "wwi:purchase_order:2",
                    "open_quantity": "3",
                },
            ],
        }
        rows = _identity_map(canonical, "batch")
        statuses = {row["canonical_id"]: row["load_status"] for row in rows}
        self.assertEqual("not_applicable", statuses["wwi:purchase_order:1"])
        self.assertEqual("not_applicable", statuses["wwi:purchase_order_line:1"])
        self.assertEqual("pending", statuses["wwi:purchase_order:2"])
        self.assertEqual("pending", statuses["wwi:purchase_order_line:2"])

    def test_twenty_pagination_uses_cursor_and_collects_supported_entities(self):
        calls = []

        def open_url(request, timeout):
            calls.append((request.full_url, request.get_method(), timeout))
            url = urlparse(request.full_url)
            params = parse_qs(url.query)
            resource = url.path.rsplit("/", 1)[-1]
            if resource == "companies" and "starting_after" not in params:
                payload = {
                    "data": {
                        "companies": [
                            {
                                "id": "company-1",
                                "wwiExternalId": "wwi:organization:customer:1",
                            }
                        ]
                    },
                    "pageInfo": {"hasNextPage": True, "endCursor": "next"},
                }
            elif resource == "companies":
                payload = {
                    "data": {"companies": [{"id": "native", "wwiExternalId": None}]},
                    "pageInfo": {"hasNextPage": False},
                }
            else:
                payload = {
                    "data": {
                        "people": [{"id": "person-1", "wwiExternalId": "wwi:contact:1"}]
                    },
                    "pageInfo": {"hasNextPage": False},
                }
            return FakeResponse(json.dumps(payload))

        client = TwentyReadClient("http://twenty", "secret", open_url=open_url)
        records = collect_twenty_readbacks(client)
        self.assertEqual(2, len(records))
        self.assertEqual(
            {"organization", "contact"}, {row["entity_type"] for row in records}
        )
        self.assertEqual(
            "next", parse_qs(urlparse(calls[1][0]).query)["starting_after"][0]
        )
        self.assertTrue(all(method == "GET" for _, method, _ in calls))

    def test_erpnext_pagination_is_ordered_and_get_only(self):
        calls = []

        def open_url(request, timeout):
            calls.append((request.full_url, request.get_method(), timeout))
            params = parse_qs(urlparse(request.full_url).query)
            start = int(params["limit_start"][0])
            page = [{"name": "SO-1"}] if start == 0 else []
            return FakeResponse(json.dumps({"data": page}))

        client = ERPNextReadClient(
            "http://erpnext", "api-key:secret", open_url=open_url
        )
        records = client.records("Sales Order", ["name"], page_size=1)
        self.assertEqual([{"name": "SO-1"}], records)
        self.assertEqual(2, len(calls))
        self.assertIn("/api/resource/Sales%20Order", calls[0][0])
        self.assertEqual(
            "name asc", parse_qs(urlparse(calls[0][0]).query)["order_by"][0]
        )
        self.assertTrue(all(method == "GET" for _, method, _ in calls))

    def test_erpnext_child_ids_are_read_through_parent_documents(self):
        class Client:
            def records(self, doctype, fields):
                source_fields = {
                    "Customer": "custom_operion_source_key",
                    "Supplier": "custom_operion_sourcekey",
                    "Item": "custom_operion_source_key",
                    "Contact": "custom_operion_source_key",
                    "Sales Order": "custom_operion_source_key",
                    "Purchase Order": "custom_operion_source_key",
                }
                if doctype not in {"Sales Order", "Purchase Order"}:
                    return []
                prefix = "sales" if doctype == "Sales Order" else "purchase"
                return [
                    {
                        "name": f"{prefix}-1",
                        source_fields[doctype]: f"wwi:{prefix}_order:1",
                    }
                ]

            def record(self, doctype, name):
                if doctype == "Sales Order":
                    return {
                        "items": [
                            {
                                "name": "sales-line-1",
                                "custom_operion_source_key_items": (
                                    "wwi:sales_order_line:1"
                                ),
                            }
                        ]
                    }
                return {
                    "items": [
                        {
                            "name": "purchase-line-1",
                            "custom_operion_source_key": "wwi:purchase_order_line:1",
                        }
                    ]
                }

        records = collect_erpnext_readbacks(Client())
        by_type = {row["entity_type"]: row["target_id"] for row in records}
        self.assertEqual("sales-line-1", by_type["sales_order_line"])
        self.assertEqual("purchase-line-1", by_type["purchase_order_line"])

    def test_reconcile_updates_selected_target_and_preserves_other_targets(self):
        rows = [
            identity_row("twenty", "wwi:contact:1", "contact"),
            identity_row("erpnext", "wwi:contact:1", "contact"),
        ]
        output, report = reconcile_identity_rows(
            rows,
            [
                {
                    "target_system": "twenty",
                    "entity_type": "contact",
                    "canonical_id": "wwi:contact:1",
                    "target_id": "person-1",
                }
            ],
            {"twenty"},
        )
        self.assertEqual("passed", report["status"])
        self.assertEqual("person-1", output[0]["target_id"])
        self.assertEqual("loaded", output[0]["load_status"])
        self.assertEqual("pending", output[1]["load_status"])

    def test_reconcile_marks_missing_and_rejects_ambiguous_readback(self):
        rows = [identity_row("twenty", "wwi:contact:1", "contact")]
        output, report = reconcile_identity_rows(rows, [], {"twenty"})
        self.assertEqual("failed", report["status"])
        self.assertEqual("missing", output[0]["load_status"])

        duplicate = {
            "target_system": "twenty",
            "entity_type": "contact",
            "canonical_id": "wwi:contact:1",
            "target_id": "person-1",
        }
        with self.assertRaises(IdentityReadbackError):
            reconcile_identity_rows(rows, [duplicate, duplicate], {"twenty"})

    def test_reconcile_preserves_intentionally_excluded_rows(self):
        excluded = identity_row("erpnext", "wwi:purchase_order:1", "purchase_order")
        excluded["load_status"] = "not_applicable"
        excluded["error"] = "excluded: no open commitment"
        output, report = reconcile_identity_rows([excluded], [], {"erpnext"})
        self.assertEqual("passed", report["status"])
        self.assertEqual(0, report["metrics"]["erpnext"]["expected"])
        self.assertEqual("not_applicable", output[0]["load_status"])

    def test_erpnext_evidence_must_match_key_and_deny_every_write_path(self):
        token = "api-key:api-secret"
        evidence = {
            "evidence_version": "erpnext-critical-readonly-v1",
            "target_system": "erpnext",
            "status": "passed",
            "observed_at": datetime.now(UTC).isoformat(),
            "api_key_fingerprint": hashlib.sha256(b"api-key").hexdigest(),
            "scope": {
                "protected_doctypes": sorted(ERPNEXT_PROTECTED_DOCTYPES),
                "known_exceptions": ["Contact", "ToDo"],
            },
            "checks": {
                doctype: {
                    "read": "allowed",
                    **dict.fromkeys(ERPNEXT_DENIED_ACTIONS, "denied"),
                }
                for doctype in ERPNEXT_PROTECTED_DOCTYPES
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            verify_erpnext_permission_evidence(path, token)
            evidence["checks"]["Customer"]["create"] = "allowed"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaises(IdentityReadbackError):
                verify_erpnext_permission_evidence(path, token)

    def test_erpnext_evidence_rejects_a_missing_protected_doctype(self):
        token = "api-key:api-secret"
        doctypes = set(ERPNEXT_PROTECTED_DOCTYPES) - {"Bin"}
        evidence = {
            "evidence_version": "erpnext-critical-readonly-v1",
            "target_system": "erpnext",
            "status": "passed",
            "observed_at": datetime.now(UTC).isoformat(),
            "api_key_fingerprint": hashlib.sha256(b"api-key").hexdigest(),
            "scope": {"protected_doctypes": sorted(doctypes)},
            "checks": {
                doctype: {
                    "read": "allowed",
                    **dict.fromkeys(ERPNEXT_DENIED_ACTIONS, "denied"),
                }
                for doctype in doctypes
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaises(IdentityReadbackError):
                verify_erpnext_permission_evidence(path, token)

    def test_erpnext_evidence_must_be_fresh(self):
        token = "api-key:api-secret"
        evidence = {
            "evidence_version": "erpnext-critical-readonly-v1",
            "target_system": "erpnext",
            "status": "passed",
            "observed_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "api_key_fingerprint": hashlib.sha256(b"api-key").hexdigest(),
            "scope": {
                "protected_doctypes": sorted(ERPNEXT_PROTECTED_DOCTYPES),
            },
            "checks": {
                doctype: {
                    "read": "allowed",
                    **dict.fromkeys(ERPNEXT_DENIED_ACTIONS, "denied"),
                }
                for doctype in ERPNEXT_PROTECTED_DOCTYPES
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaises(IdentityReadbackError):
                verify_erpnext_permission_evidence(path, token)


if __name__ == "__main__":
    unittest.main()
