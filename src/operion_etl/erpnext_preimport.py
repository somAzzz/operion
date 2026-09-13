from __future__ import annotations

import csv
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .pipeline import (
    ERPNEXT_COMPANY,
    ERPNEXT_CONTACT_HEADERS,
    ERPNEXT_CURRENCY,
    ERPNEXT_CUSTOMER_HEADERS,
    ERPNEXT_ITEM_HEADERS,
    ERPNEXT_PURCHASE_ORDER_HEADERS,
    ERPNEXT_SALES_ORDER_HEADERS,
    ERPNEXT_SUPPLIER_HEADERS,
    ERPNEXT_TERRITORY,
)


FILE_HEADERS = {
    "customers.csv": ERPNEXT_CUSTOMER_HEADERS,
    "suppliers.csv": ERPNEXT_SUPPLIER_HEADERS,
    "items.csv": ERPNEXT_ITEM_HEADERS,
    "contacts.csv": ERPNEXT_CONTACT_HEADERS,
    "sales_orders.csv": ERPNEXT_SALES_ORDER_HEADERS,
    "purchase_orders.csv": ERPNEXT_PURCHASE_ORDER_HEADERS,
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def validate_erpnext_imports(files: dict[str, list[dict[str, str]]]) -> dict:
    errors: list[dict[str, object]] = []

    def issue(filename: str, row: int, field: str, message: str) -> None:
        errors.append({"file": filename, "row": row, "field": field, "message": message})

    def check_unique_keys(filename: str, rows: list[dict[str, str]]) -> None:
        keys = [row.get("Operion Source Key", "").strip() for row in rows]
        duplicates = {key for key, count in Counter(keys).items() if key and count > 1}
        for index, (row, key) in enumerate(zip(rows, keys, strict=True), start=2):
            if row.get("ID", "").strip():
                issue(filename, index, "ID", "leave native ERPNext ID blank for insert")
            if not key:
                issue(filename, index, "Operion Source Key", "source identity is required")
            elif key in duplicates:
                issue(filename, index, "Operion Source Key", "duplicate source identity")

    customers = files["customers.csv"]
    suppliers = files["suppliers.csv"]
    items = files["items.csv"]
    contacts = files["contacts.csv"]
    check_unique_keys("customers.csv", customers)
    check_unique_keys("suppliers.csv", suppliers)
    check_unique_keys("items.csv", items)
    check_unique_keys("contacts.csv", contacts)

    customer_names = {row.get("Customer Name", "").strip() for row in customers} - {""}
    supplier_names = {row.get("Supplier Name", "").strip() for row in suppliers} - {""}
    item_codes = {row.get("Item Code", "").strip() for row in items} - {""}

    for index, row in enumerate(customers, start=2):
        if not row.get("Customer Name", "").strip():
            issue("customers.csv", index, "Customer Name", "customer name is required")
        if row.get("Customer Group", "").strip() != "Commercial":
            issue("customers.csv", index, "Customer Group", "expected existing group Commercial")
        if row.get("Territory", "").strip() != ERPNEXT_TERRITORY:
            issue("customers.csv", index, "Territory", f"expected leaf territory {ERPNEXT_TERRITORY}")

    for index, row in enumerate(suppliers, start=2):
        if not row.get("Supplier Name", "").strip():
            issue("suppliers.csv", index, "Supplier Name", "supplier name is required")
        if row.get("Supplier Group", "").strip() != "All Supplier Groups":
            issue("suppliers.csv", index, "Supplier Group", "expected existing supplier group")

    for index, row in enumerate(items, start=2):
        code = row.get("Item Code", "").strip()
        if not code:
            issue("items.csv", index, "Item Code", "item code is required")
        if row.get("Default Unit of Measure", "").strip() != "Unit":
            issue("items.csv", index, "Default Unit of Measure", "WWI Each must map to existing UOM Unit")
        if row.get("Maintain Stock", "").strip() not in {"1", "Yes"}:
            issue("items.csv", index, "Maintain Stock", "stock item must be enabled")

    for index, row in enumerate(contacts, start=2):
        if not row.get("First Name", "").strip():
            issue("contacts.csv", index, "First Name", "contact first name is required")
        doctype = row.get("Link Document Type (Links)", "").strip()
        name = row.get("Link Name (Links)", "").strip()
        if bool(doctype) != bool(name):
            issue("contacts.csv", index, "Link Name (Links)", "link type and link name must both be set or both blank")
        elif doctype == "Customer" and name not in customer_names:
            issue("contacts.csv", index, "Link Name (Links)", "customer relation does not resolve")
        elif doctype == "Supplier" and name not in supplier_names:
            issue("contacts.csv", index, "Link Name (Links)", "supplier relation does not resolve")
        elif doctype and doctype not in {"Customer", "Supplier"}:
            issue("contacts.csv", index, "Link Document Type (Links)", "unsupported relation type")

    metrics: dict[str, int] = {
        "customers": len(customers),
        "suppliers": len(suppliers),
        "items": len(items),
        "contacts": len(contacts),
    }

    def check_orders(
        filename: str,
        parent_key: str,
        relation_field: str,
        valid_relations: set[str],
        child_start: str,
    ) -> None:
        rows = files[filename]
        headers = FILE_HEADERS[filename]
        parent_headers = headers[:headers.index(child_start)]
        parent_keys: list[str] = []
        child_keys: list[str] = []
        active_parent = ""
        parent_count = 0
        for index, row in enumerate(rows, start=2):
            source_key = row.get(parent_key, "").strip()
            if source_key:
                active_parent = source_key
                parent_keys.append(source_key)
                parent_count += 1
                if row.get("ID", "").strip():
                    issue(filename, index, "ID", "leave native ERPNext ID blank for insert")
                if row.get(relation_field, "").strip() not in valid_relations:
                    issue(filename, index, relation_field, "parent relation does not resolve to imported master")
                if row.get("Company", "").strip() != ERPNEXT_COMPANY:
                    issue(filename, index, "Company", f"expected {ERPNEXT_COMPANY}")
                if row.get("Currency", "").strip() != ERPNEXT_CURRENCY:
                    issue(filename, index, "Currency", f"expected {ERPNEXT_CURRENCY}")
                if row.get("Exchange Rate", "").strip() != "1":
                    issue(filename, index, "Exchange Rate", "demo target-currency mapping requires exchange rate 1")
            else:
                if not active_parent:
                    issue(filename, index, parent_key, "child row appears before a parent row")
                for field in parent_headers:
                    if row.get(field, "").strip():
                        issue(filename, index, field, "continuation child row must leave all parent columns blank")

            item_code = row.get("Item Code (Items)", "").strip()
            child_key = row.get("Operion Source Key (Items)", "").strip()
            if item_code not in item_codes:
                issue(filename, index, "Item Code (Items)", "item relation does not resolve")
            if not child_key:
                issue(filename, index, "Operion Source Key (Items)", "child source identity is required")
            child_keys.append(child_key)
            quantity = _decimal(row.get("Quantity (Items)", ""))
            rate = _decimal(row.get("Rate (Items)", ""))
            amount = _decimal(row.get("Amount (Items)", ""))
            if quantity is None or quantity <= 0:
                issue(filename, index, "Quantity (Items)", "open commitment quantity must be positive")
            if rate is None or rate < 0:
                issue(filename, index, "Rate (Items)", "rate must be a non-negative number")
            if quantity is not None and rate is not None and amount is not None:
                if abs(quantity * rate - amount) > Decimal("0.01"):
                    issue(filename, index, "Amount (Items)", "amount does not equal quantity times rate")
            else:
                issue(filename, index, "Amount (Items)", "quantity, rate, and amount must be numeric")
            for field in ("Stock UOM (Items)", "UOM (Items)"):
                if row.get(field, "").strip() != "Unit":
                    issue(filename, index, field, "expected existing UOM Unit")
            if row.get("UOM Conversion Factor (Items)", "").strip() != "1":
                issue(filename, index, "UOM Conversion Factor (Items)", "expected conversion factor 1")

        for value, count in Counter(parent_keys).items():
            if count > 1:
                issue(filename, 0, parent_key, f"duplicate parent source identity: {value}")
        for value, count in Counter(child_keys).items():
            if value and count > 1:
                issue(filename, 0, "Operion Source Key (Items)", f"duplicate child source identity: {value}")
        metric_prefix = "sales_orders" if filename == "sales_orders.csv" else "purchase_orders"
        metrics[metric_prefix] = parent_count
        metrics[f"{metric_prefix}_items"] = len(rows)

    check_orders(
        "sales_orders.csv", "Operion Source Key", "Customer", customer_names,
        "Item Code (Items)",
    )
    check_orders(
        "purchase_orders.csv", "Operion Source Key", "Supplier", supplier_names,
        "Item Code (Items)",
    )

    return {
        "status": "passed" if not errors else "failed",
        "metrics": metrics,
        "errors": errors,
        "manual_prerequisites": [
            "Create the listed Operion/WWI custom fields before importing these headers.",
            "Create and enable Fiscal Year 2016 before importing the historical orders.",
            "The WWI sample does not declare a currency; this demo batch maps amounts to EUR at exchange rate 1.",
        ],
    }


def validate_directory(directory: Path, report: Path | None = None) -> dict:
    files: dict[str, list[dict[str, str]]] = {}
    header_errors: list[dict[str, object]] = []
    for filename, expected_headers in FILE_HEADERS.items():
        path = directory / filename
        if not path.is_file():
            header_errors.append({
                "file": filename, "row": 1, "field": "", "message": "required file is missing",
            })
            files[filename] = []
            continue
        actual_headers, rows = _read_csv(path)
        files[filename] = rows
        if actual_headers != expected_headers:
            header_errors.append({
                "file": filename, "row": 1, "field": "headers",
                "message": "headers do not exactly match the ERPNext import template",
            })
    result = validate_erpnext_imports(files)
    if header_errors:
        result["errors"] = header_errors + result["errors"]
        result["status"] = "failed"
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
