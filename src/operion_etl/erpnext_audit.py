from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _same_number(expected: Any, actual: Any) -> bool:
    left, right = _decimal(expected), _decimal(actual)
    return (
        left is not None and right is not None and abs(left - right) <= Decimal("0.01")
    )


class FrappeBenchClient:
    """Read-only Frappe API client executed inside the local ERPNext backend."""

    def __init__(self, container: str, site: str):
        self.container = container
        self.site = site

    def get_all(
        self,
        doctype: str,
        fields: list[str],
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "doctype": doctype,
            "fields": fields,
            "limit_page_length": 0,
        }
        if filters:
            kwargs["filters"] = filters
        if order_by:
            kwargs["order_by"] = order_by
        result = subprocess.run(
            [
                "docker",
                "exec",
                self.container,
                "bench",
                "--site",
                self.site,
                "execute",
                "frappe.get_all",
                "--kwargs",
                json.dumps(kwargs),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout.strip() or "[]")


def _source_fields(
    client: FrappeBenchClient,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    custom_fields = client.get_all(
        "Custom Field",
        ["name", "dt", "label", "fieldname", "unique"],
        order_by="dt asc, idx asc",
    )
    source_fields = {
        row["dt"]: row["fieldname"]
        for row in custom_fields
        if row.get("label") == "Operion Source Key"
    }
    return source_fields, custom_fields


def _orders(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    active = ""
    for row in rows:
        if row.get("Operion Source Key", "").strip():
            active = row["Operion Source Key"].strip()
            result[active] = {"parent": row, "items": []}
        if active:
            result[active]["items"].append(row)
    return result


def audit_directory(
    directory: Path,
    client: FrappeBenchClient,
    report: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    def issue(scope: str, key: str, field: str, expected: Any, actual: Any) -> None:
        errors.append(
            {
                "scope": scope,
                "key": key,
                "field": field,
                "expected": expected,
                "actual": actual,
            }
        )

    source_fields, custom_fields = _source_fields(client)
    required_source_doctypes = [
        "Customer",
        "Supplier",
        "Item",
        "Contact",
        "Sales Order",
        "Sales Order Item",
        "Purchase Order",
        "Purchase Order Item",
    ]
    for doctype in required_source_doctypes:
        if doctype not in source_fields:
            issue(
                "schema",
                doctype,
                "Operion Source Key",
                "exact label on this DocType",
                "missing",
            )
    for row in custom_fields:
        if (
            row.get("dt") in required_source_doctypes
            and row.get("label") == "Operion Source Key"
            and not int(row.get("unique") or 0)
        ):
            warnings.append(
                {
                    "scope": "schema",
                    "key": row["dt"],
                    "field": row["fieldname"],
                    "message": "custom source key exists but is not database-unique",
                }
            )
        if (
            row.get("dt") in {"Sales Order", "Purchase Order"}
            and row.get("label") == "Operion Source Key (Items)"
        ):
            warnings.append(
                {
                    "scope": "schema",
                    "key": row["dt"],
                    "field": row["fieldname"],
                    "message": "redundant child-style field exists on the parent DocType",
                }
            )
        if (
            row.get("dt") in {"Sales Order Item", "Purchase Order Item"}
            and row.get("label") == "Operion Source Key (Items)"
        ):
            warnings.append(
                {
                    "scope": "schema",
                    "key": row["dt"],
                    "field": row["fieldname"],
                    "message": "child field label must be exactly Operion Source Key; ERPNext adds (Items) only to the CSV header",
                }
            )

    def audit_master(
        filename: str,
        doctype: str,
        csv_key: str,
        fields: dict[str, str],
        numeric: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        expected_rows = _read_csv(directory / filename)
        source_field = source_fields.get(doctype)
        if not source_field:
            return {}
        actual_rows = client.get_all(doctype, ["name", source_field, *fields.values()])
        actual = {
            str(row.get(source_field) or ""): row
            for row in actual_rows
            if str(row.get(source_field) or "").startswith("wwi:")
        }
        expected = {row[csv_key]: row for row in expected_rows}
        metrics[doctype] = {"expected": len(expected), "actual": len(actual)}
        if set(expected) != set(actual):
            issue(
                doctype, "source keys", source_field, sorted(expected), sorted(actual)
            )
        for key in sorted(set(expected) & set(actual)):
            for csv_field, target_field in fields.items():
                left, right = (
                    expected[key].get(csv_field, ""),
                    actual[key].get(target_field),
                )
                matches = (
                    _same_number(left, right)
                    if numeric and csv_field in numeric
                    else str(left) == str(right or "")
                )
                if not matches:
                    issue(doctype, key, target_field, left, right)
        return actual

    audit_master(
        "customers.csv",
        "Customer",
        "Operion Source Key",
        {
            "Customer Name": "customer_name",
            "Customer Type": "customer_type",
            "Customer Group": "customer_group",
            "Territory": "territory",
        },
    )
    audit_master(
        "suppliers.csv",
        "Supplier",
        "Operion Source Key",
        {
            "Supplier Name": "supplier_name",
            "Supplier Type": "supplier_type",
            "Supplier Group": "supplier_group",
        },
    )
    items = audit_master(
        "items.csv",
        "Item",
        "Operion Source Key",
        {
            "Item Code": "item_code",
            "Item Name": "item_name",
            "Item Group": "item_group",
            "Default Unit of Measure": "stock_uom",
            "Maintain Stock": "is_stock_item",
            "Standard Selling Rate": "standard_rate",
        },
        {"Maintain Stock", "Standard Selling Rate"},
    )

    contacts_expected = {
        row["Operion Source Key"]: row for row in _read_csv(directory / "contacts.csv")
    }
    contact_field = source_fields.get("Contact")
    contacts: dict[str, dict[str, Any]] = {}
    if contact_field:
        contact_rows = client.get_all(
            "Contact", ["name", contact_field, "first_name", "last_name"]
        )
        contacts = {
            str(row.get(contact_field) or ""): row
            for row in contact_rows
            if str(row.get(contact_field) or "").startswith("wwi:")
        }
        metrics["Contact"] = {
            "expected": len(contacts_expected),
            "actual": len(contacts),
        }
        if set(contacts_expected) != set(contacts):
            issue(
                "Contact",
                "source keys",
                contact_field,
                sorted(contacts_expected),
                sorted(contacts),
            )
        names = [row["name"] for row in contacts.values()]
        email_rows = client.get_all(
            "Contact Email", ["parent", "email_id", "is_primary"]
        )
        phone_rows = client.get_all(
            "Contact Phone", ["parent", "phone", "is_primary_phone"]
        )
        link_rows = client.get_all(
            "Dynamic Link",
            ["parent", "link_doctype", "link_name"],
            {"parenttype": "Contact"},
        )
        emails = defaultdict(list)
        phones = defaultdict(list)
        links = defaultdict(list)
        for row in email_rows:
            if row["parent"] in names:
                emails[row["parent"]].append(row)
        for row in phone_rows:
            if row["parent"] in names:
                phones[row["parent"]].append(row)
        for row in link_rows:
            if row["parent"] in names:
                links[row["parent"]].append(row)
        for key in sorted(set(contacts_expected) & set(contacts)):
            expected, actual = contacts_expected[key], contacts[key]
            for csv_field, target_field in (
                ("First Name", "first_name"),
                ("Last Name", "last_name"),
            ):
                if expected.get(csv_field, "") != str(actual.get(target_field) or ""):
                    issue(
                        "Contact",
                        key,
                        target_field,
                        expected.get(csv_field, ""),
                        actual.get(target_field),
                    )
            actual_emails = {
                (row["email_id"], int(row.get("is_primary") or 0))
                for row in emails[actual["name"]]
            }
            expected_email = (expected["Email ID (Email IDs)"], 1)
            if expected_email not in actual_emails:
                issue(
                    "Contact", key, "email_ids", expected_email, sorted(actual_emails)
                )
            actual_phones = {
                (row["phone"], int(row.get("is_primary_phone") or 0))
                for row in phones[actual["name"]]
            }
            expected_phone = (expected["Number (Contact Numbers)"], 1)
            if expected_phone not in actual_phones:
                issue(
                    "Contact", key, "phone_nos", expected_phone, sorted(actual_phones)
                )
            expected_link = (
                expected["Link Document Type (Links)"],
                expected["Link Name (Links)"],
            )
            actual_links = {
                (row["link_doctype"], row["link_name"]) for row in links[actual["name"]]
            }
            if expected_link[0] and expected_link not in actual_links:
                issue("Contact", key, "links", expected_link, sorted(actual_links))

    def audit_orders(
        filename: str, doctype: str, child_doctype: str, relation_field: str
    ) -> None:
        expected = _orders(_read_csv(directory / filename))
        parent_field, child_field = (
            source_fields.get(doctype),
            source_fields.get(child_doctype),
        )
        if not parent_field:
            return
        target_due = "delivery_date" if doctype == "Sales Order" else "schedule_date"
        actual_rows = client.get_all(
            doctype,
            [
                "name",
                parent_field,
                relation_field,
                "transaction_date",
                target_due,
                "company",
                "currency",
                "conversion_rate",
                "total",
                "docstatus",
            ],
        )
        actual = {
            str(row.get(parent_field) or ""): row
            for row in actual_rows
            if str(row.get(parent_field) or "").startswith("wwi:")
        }
        metrics[doctype] = {"expected": len(expected), "actual": len(actual)}
        if set(expected) != set(actual):
            issue(
                doctype, "source keys", parent_field, sorted(expected), sorted(actual)
            )
        parent_names = {row["name"]: key for key, row in actual.items()}
        child_fields = [
            "parent",
            "item_code",
            "qty",
            "uom",
            "stock_uom",
            "conversion_factor",
            "rate",
            "amount",
            target_due,
        ]
        if child_field:
            child_fields.append(child_field)
        child_rows = client.get_all(child_doctype, child_fields)
        children = defaultdict(list)
        for row in child_rows:
            if row["parent"] in parent_names:
                children[parent_names[row["parent"]]].append(row)
        metrics[f"{doctype} Item"] = {
            "expected": sum(len(value["items"]) for value in expected.values()),
            "actual": sum(len(value) for value in children.values()),
        }
        for key in sorted(set(expected) & set(actual)):
            expected_parent, actual_parent = expected[key]["parent"], actual[key]
            csv_relation = "Customer" if doctype == "Sales Order" else "Supplier"
            csv_due = "Delivery Date" if doctype == "Sales Order" else "Required By"
            comparisons = {
                relation_field: expected_parent[csv_relation],
                "transaction_date": expected_parent["Date"],
                target_due: expected_parent[csv_due],
                "company": expected_parent["Company"],
                "currency": expected_parent["Currency"],
                "conversion_rate": expected_parent["Exchange Rate"],
            }
            for target_field, expected_value in comparisons.items():
                actual_value = actual_parent.get(target_field)
                numeric = target_field == "conversion_rate"
                if not (
                    _same_number(expected_value, actual_value)
                    if numeric
                    else str(expected_value) == str(actual_value or "")
                ):
                    issue(doctype, key, target_field, expected_value, actual_value)
            expected_items = expected[key]["items"]
            expected_total = sum(
                (_decimal(row["Amount (Items)"]) or Decimal("0"))
                for row in expected_items
            )
            if not _same_number(expected_total, actual_parent.get("total")):
                issue(doctype, key, "total", expected_total, actual_parent.get("total"))
            if child_field:
                expected_keys = {
                    row["Operion Source Key (Items)"] for row in expected_items
                }
                actual_keys = {str(row.get(child_field) or "") for row in children[key]}
                if expected_keys != actual_keys:
                    issue(
                        child_doctype,
                        key,
                        child_field,
                        sorted(expected_keys),
                        sorted(actual_keys),
                    )

            def signature(row: dict[str, Any], expected_row: bool) -> tuple[Any, ...]:
                if expected_row:
                    date_field = (
                        "Delivery Date (Items)"
                        if doctype == "Sales Order"
                        else "Required By (Items)"
                    )
                    return (
                        row["Item Code (Items)"],
                        row[date_field],
                        _decimal(row["Quantity (Items)"]),
                        row["UOM (Items)"],
                        _decimal(row["Rate (Items)"]),
                        _decimal(row["Amount (Items)"]),
                    )
                return (
                    row["item_code"],
                    str(row.get(target_due) or ""),
                    _decimal(row["qty"]),
                    row["uom"],
                    _decimal(row["rate"]),
                    _decimal(row["amount"]),
                )

            expected_signatures = Counter(
                signature(row, True) for row in expected_items
            )
            actual_signatures = Counter(signature(row, False) for row in children[key])
            if expected_signatures != actual_signatures:
                issue(
                    child_doctype,
                    key,
                    "item rows",
                    sorted(map(str, expected_signatures.elements())),
                    sorted(map(str, actual_signatures.elements())),
                )

    audit_orders("sales_orders.csv", "Sales Order", "Sales Order Item", "customer")
    audit_orders(
        "purchase_orders.csv", "Purchase Order", "Purchase Order Item", "supplier"
    )

    item_codes = {row["item_code"] for row in items.values()}
    item_prices = client.get_all(
        "Item Price", ["item_code", "price_list", "price_list_rate"]
    )
    relevant_prices = [row for row in item_prices if row["item_code"] in item_codes]
    price_counts = Counter(
        (row["item_code"], row["price_list"]) for row in relevant_prices
    )
    for item_code in sorted(item_codes):
        for price_list in ("Standard Selling", "Standard Buying"):
            if price_counts[(item_code, price_list)] != 1:
                issue(
                    "Item Price",
                    item_code,
                    price_list,
                    1,
                    price_counts[(item_code, price_list)],
                )
    expected_prices: dict[tuple[str, str], set[Decimal]] = defaultdict(set)
    for row in _read_csv(directory / "items.csv"):
        expected_prices[(row["Item Code"], "Standard Selling")].add(
            _decimal(row["Standard Selling Rate"]) or Decimal("0")
        )
    for order in _orders(_read_csv(directory / "purchase_orders.csv")).values():
        for row in order["items"]:
            expected_prices[(row["Item Code (Items)"], "Standard Buying")].add(
                _decimal(row["Rate (Items)"]) or Decimal("0")
            )
    for key, rates in sorted(expected_prices.items()):
        if len(rates) != 1:
            issue(
                "Item Price", key[0], key[1], "one source rate", sorted(map(str, rates))
            )
            continue
        actual_rates = [
            row["price_list_rate"]
            for row in relevant_prices
            if (row["item_code"], row["price_list"]) == key
        ]
        if len(actual_rates) == 1 and not _same_number(
            next(iter(rates)), actual_rates[0]
        ):
            issue("Item Price", key[0], key[1], next(iter(rates)), actual_rates[0])
    metrics["Item Price"] = {
        "actual": len(relevant_prices),
        "duplicates": sum(count > 1 for count in price_counts.values()),
    }

    fiscal_years = client.get_all(
        "Fiscal Year", ["name", "year_start_date", "year_end_date", "disabled"]
    )
    active_2016 = [
        row
        for row in fiscal_years
        if str(row.get("year_start_date", "")) <= "2016-01-01"
        and str(row.get("year_end_date", "")) >= "2016-12-31"
        and not int(row.get("disabled") or 0)
    ]
    metrics["Fiscal Year 2016"] = {"active_matches": len(active_2016)}
    if not active_2016:
        issue("Fiscal Year", "2016", "active period", "covers 2016", "missing")

    result = {
        "status": "passed" if not errors else "failed",
        "audited_at": datetime.now(UTC).isoformat(),
        "backend": {
            "type": "frappe-bench-api",
            "container": client.container,
            "site": client.site,
        },
        "directory": str(directory),
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
    }
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    return result


def audit_erpnext(
    directory: Path, container: str, site: str, report: Path | None = None
) -> dict[str, Any]:
    return audit_directory(directory, FrappeBenchClient(container, site), report)
