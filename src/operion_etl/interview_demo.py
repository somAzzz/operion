from __future__ import annotations

import csv
import json
import random
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .e2_data import ERPNextAdminClient, _find_one
from .identity_readback import IDENTITY_FIELDS
from .twenty import TwentyClient, read_env

DATASET_VERSION = "interview-demo-v1"
SOURCE_PREFIX = "operion:demo:interview-v1"
DEFAULT_BUSINESS_DATE = date(2026, 9, 15)
DEFAULT_SEED = 42

CUSTOMER_NAMES = (
    "DEMO Northstar Packaging GmbH",
    "DEMO Northstar Packaging Nord GmbH",
    "DEMO Blue Harbor Supplies GmbH",
    "DEMO Cedar Works AG",
    "DEMO Juniper Office GmbH",
    "DEMO Lantern Logistics GmbH",
    "DEMO Meadow Retail GmbH",
    "DEMO Quartz Workshop GmbH",
    "DEMO Riverbend Services GmbH",
    "DEMO Summit Sample GmbH",
)
SUPPLIER_NAMES = (
    "DEMO Atlas Cartons GmbH",
    "DEMO Birch Consumables GmbH",
    "DEMO Copper Label Works GmbH",
    "DEMO Delta Pallet Supply GmbH",
    "DEMO Elm Protective Goods GmbH",
)
PRODUCTS = (
    ("Recycled shipping carton S", "Unit", "1.85"),
    ("Recycled shipping carton M", "Unit", "2.40"),
    ("Recycled shipping carton L", "Unit", "3.20"),
    ("Paper packing tape 50 mm", "Roll", "3.75"),
    ("Water-activated tape 70 mm", "Roll", "5.60"),
    ("Kraft void-fill paper", "Kilogram", "2.95"),
    ("Reusable pallet wrap", "Roll", "8.40"),
    ("Compostable mailer S", "Unit", "0.48"),
    ("Compostable mailer L", "Unit", "0.72"),
    ("Thermal shipping label", "Pack", "12.50"),
    ("Corner protector set", "Pack", "6.80"),
    ("Document pouch", "Pack", "9.90"),
)

FILE_FIELDS: dict[str, list[str]] = {
    "organizations": [
        "canonical_id",
        "source_system",
        "source_id",
        "name",
        "roles",
        "primary_contact_source_id",
        "phone",
        "website",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "country",
        "postal_code",
        "payment_days",
        "credit_limit",
        "created_at",
        "updated_at",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "contacts": [
        "canonical_id",
        "source_system",
        "source_id",
        "full_name",
        "preferred_name",
        "email",
        "phone",
        "company_canonical_id",
        "is_employee",
        "is_salesperson",
        "relationship",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "products": [
        "canonical_id",
        "source_system",
        "source_id",
        "name",
        "supplier_source_id",
        "uom",
        "outer_uom",
        "units_per_outer",
        "brand",
        "size",
        "barcode",
        "unit_price_ex_tax",
        "tax_rate_percent",
        "quantity_on_hand",
        "warehouse",
        "bin_location",
        "currency",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "sales_orders": [
        "canonical_id",
        "source_system",
        "source_id",
        "customer_canonical_id",
        "contact_canonical_id",
        "salesperson_canonical_id",
        "order_date",
        "expected_delivery_date",
        "customer_po_number",
        "source_status",
        "docstatus",
        "business_status",
        "currency",
        "net_total_ex_tax",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "sales_order_lines": [
        "canonical_id",
        "source_system",
        "source_id",
        "sales_order_canonical_id",
        "product_canonical_id",
        "description",
        "uom",
        "ordered_quantity",
        "delivered_quantity",
        "open_quantity",
        "unit_price_ex_tax",
        "tax_rate_percent",
        "net_amount",
        "currency",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "purchase_orders": [
        "canonical_id",
        "source_system",
        "source_id",
        "supplier_canonical_id",
        "contact_canonical_id",
        "order_date",
        "expected_delivery_date",
        "supplier_reference",
        "source_status",
        "docstatus",
        "business_status",
        "currency",
        "net_total_ex_tax",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "purchase_order_lines": [
        "canonical_id",
        "source_system",
        "source_id",
        "purchase_order_canonical_id",
        "product_canonical_id",
        "description",
        "source_uom",
        "canonical_uom",
        "units_per_outer",
        "ordered_outers",
        "received_outers",
        "open_quantity",
        "expected_unit_price_per_outer",
        "expected_unit_price_each",
        "net_amount",
        "currency",
        "last_receipt_date",
        "data_class",
        "dataset_version",
        "business_date",
        "seed",
    ],
    "fulfillment_scenarios": [
        "case_id",
        "scenario_version",
        "scenario_type",
        "derived_from",
        "business_date",
        "timezone",
        "promise_scope",
        "promise_date",
        "warehouse",
        "product_canonical_id",
        "uom",
        "ordered_quantity",
        "delivered_quantity",
        "remaining_quantity",
        "on_hand_quantity",
        "reserved_for_other_orders",
        "current_order_in_reservations",
        "unallocated_inbound_quantity",
        "expected_inbound_date",
        "expected_result",
        "data_class",
        "on_hand_source",
        "reservation_source",
        "inbound_source",
        "fulfillment_source",
    ],
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=FILE_FIELDS[path.stem], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _common(business_date: date, seed: int) -> dict[str, str]:
    return {
        "data_class": "simulated",
        "dataset_version": DATASET_VERSION,
        "business_date": business_date.isoformat(),
        "seed": str(seed),
    }


def build_interview_demo(
    business_date: date = DEFAULT_BUSINESS_DATE,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    common = _common(business_date, seed)
    organizations: list[dict[str, Any]] = []
    for role, names in (("customer", CUSTOMER_NAMES), ("supplier", SUPPLIER_NAMES)):
        for index, name in enumerate(names, 1):
            key = f"{SOURCE_PREFIX}:{role}:{index:03d}"
            organizations.append(
                {
                    "canonical_id": key,
                    "source_system": "operion",
                    "source_id": f"{role}-{index:03d}",
                    "name": name,
                    "roles": role,
                    "primary_contact_source_id": f"{role}-{index:03d}-contact-01",
                    "phone": "",
                    "website": f"https://{role}-{index:03d}.example.invalid",
                    "address_line_1": f"Demo Street {index}",
                    "address_line_2": "",
                    "city": "Berlin" if index % 2 else "Hamburg",
                    "state": "Berlin" if index % 2 else "Hamburg",
                    "country": "Germany",
                    "postal_code": f"10{index:03d}",
                    "payment_days": "",
                    "credit_limit": "",
                    "created_at": business_date.isoformat(),
                    "updated_at": f"{business_date.isoformat()}T09:00:00+02:00",
                    **common,
                }
            )

    first_names = (
        "Avery",
        "Blair",
        "Casey",
        "Devon",
        "Emery",
        "Finley",
        "Gray",
        "Harper",
        "Indigo",
        "Jordan",
        "Kai",
        "Lane",
        "Morgan",
        "Noel",
        "Oakley",
        "Parker",
        "Quinn",
        "Riley",
        "Sage",
        "Taylor",
    )
    contacts: list[dict[str, Any]] = []
    assignments = (
        [("customer", i) for i in range(1, 11)]
        + [("customer", i) for i in range(1, 6)]
        + [("supplier", i) for i in range(1, 6)]
    )
    for index, (role, org_index) in enumerate(assignments, 1):
        org_key = f"{SOURCE_PREFIX}:{role}:{org_index:03d}"
        contact_no = 1 if index <= 10 or role == "supplier" else 2
        source_id = f"{role}-{org_index:03d}-contact-{contact_no:02d}"
        first = first_names[index - 1]
        contacts.append(
            {
                "canonical_id": f"{SOURCE_PREFIX}:contact:{index:03d}",
                "source_system": "operion",
                "source_id": source_id,
                "full_name": f"{first} Example",
                "preferred_name": first,
                "email": f"{first.casefold()}.{index:03d}@example.invalid",
                "phone": "",
                "company_canonical_id": org_key,
                "is_employee": "false",
                "is_salesperson": "false",
                "relationship": "customer contact"
                if role == "customer"
                else "supplier contact",
                **common,
            }
        )

    products: list[dict[str, Any]] = []
    for index, (name, uom, price) in enumerate(PRODUCTS, 1):
        products.append(
            {
                "canonical_id": f"{SOURCE_PREFIX}:product:{index:03d}",
                "source_system": "operion",
                "source_id": f"product-{index:03d}",
                "name": f"DEMO {name}",
                "supplier_source_id": f"supplier-{((index - 1) % 4) + 1:03d}",
                "uom": uom,
                "outer_uom": uom,
                "units_per_outer": "1",
                "brand": "DEMO Neutral Supply",
                "size": "",
                "barcode": "",
                "unit_price_ex_tax": price,
                "tax_rate_percent": "19",
                "quantity_on_hand": "",
                "warehouse": "",
                "bin_location": "",
                "currency": "EUR",
                **common,
            }
        )

    contact_by_org: dict[str, str] = {}
    for row in contacts:
        contact_by_org.setdefault(row["company_canonical_id"], row["canonical_id"])

    sales_orders: list[dict[str, Any]] = []
    sales_lines: list[dict[str, Any]] = []
    distribution = (9, 4, 4, 3, 3, 2, 2, 2, 1, 0)
    order_number = 1
    line_number = 1
    for customer_index, count in enumerate(distribution, 1):
        customer_key = f"{SOURCE_PREFIX}:customer:{customer_index:03d}"
        for local_index in range(count):
            order_key = f"{SOURCE_PREFIX}:sales-order:{order_number:03d}"
            order_date = business_date + timedelta(days=((order_number * 7) % 91) - 45)
            delivery_date = order_date + timedelta(days=3 + order_number % 8)
            status, docstatus = (
                ("draft", "0")
                if order_number % 7 == 0
                else ("completed", "1")
                if order_number % 5 == 0
                else ("to_deliver", "1")
            )
            line_count = 1 + rng.randrange(4)
            total = Decimal("0")
            for item_offset in range(line_count):
                product_index = (
                    (order_number + item_offset * 3 - 1) % len(PRODUCTS)
                ) + 1
                product = products[product_index - 1]
                quantity = Decimal(str(2 + rng.randrange(24)))
                rate = (
                    Decimal(product["unit_price_ex_tax"])
                    + Decimal(str(customer_index)) / 10
                )
                amount = quantity * rate
                delivered = quantity if status == "completed" else Decimal("0")
                total += amount
                sales_lines.append(
                    {
                        "canonical_id": f"{SOURCE_PREFIX}:sales-order-line:{line_number:03d}",
                        "source_system": "operion",
                        "source_id": f"sales-order-line-{line_number:03d}",
                        "sales_order_canonical_id": order_key,
                        "product_canonical_id": product["canonical_id"],
                        "description": product["name"],
                        "uom": product["uom"],
                        "ordered_quantity": str(quantity),
                        "delivered_quantity": str(delivered),
                        "open_quantity": str(quantity - delivered),
                        "unit_price_ex_tax": _money(rate),
                        "tax_rate_percent": "19",
                        "net_amount": _money(amount),
                        "currency": "EUR",
                        **common,
                    }
                )
                line_number += 1
            sales_orders.append(
                {
                    "canonical_id": order_key,
                    "source_system": "operion",
                    "source_id": f"sales-order-{order_number:03d}",
                    "customer_canonical_id": customer_key,
                    "contact_canonical_id": contact_by_org[customer_key],
                    "salesperson_canonical_id": "",
                    "order_date": order_date.isoformat(),
                    "expected_delivery_date": delivery_date.isoformat(),
                    "customer_po_number": f"DEMO-SO-{order_number:03d}",
                    "source_status": status,
                    "docstatus": docstatus,
                    "business_status": status,
                    "currency": "EUR",
                    "net_total_ex_tax": _money(total),
                    **common,
                }
            )
            order_number += 1

    purchase_orders: list[dict[str, Any]] = []
    purchase_lines: list[dict[str, Any]] = []
    purchase_number = 1
    purchase_line_number = 1
    for supplier_index, count in enumerate((5, 4, 3, 3, 0), 1):
        supplier_key = f"{SOURCE_PREFIX}:supplier:{supplier_index:03d}"
        for _ in range(count):
            order_key = f"{SOURCE_PREFIX}:purchase-order:{purchase_number:03d}"
            order_date = business_date + timedelta(
                days=((purchase_number * 11) % 81) - 40
            )
            required = order_date + timedelta(days=5 + purchase_number % 9)
            status, docstatus = (
                ("draft", "0")
                if purchase_number % 6 == 0
                else ("completed", "1")
                if purchase_number % 5 == 0
                else ("to_receive", "1")
            )
            line_count = 1 + rng.randrange(4)
            total = Decimal("0")
            for item_offset in range(line_count):
                product_index = (
                    (purchase_number * 2 + item_offset - 1) % len(PRODUCTS)
                ) + 1
                product = products[product_index - 1]
                quantity = Decimal(str(10 + rng.randrange(50)))
                rate = (
                    Decimal(product["unit_price_ex_tax"]) * Decimal("0.62")
                ).quantize(Decimal("0.01"))
                amount = quantity * rate
                received = quantity if status == "completed" else Decimal("0")
                total += amount
                purchase_lines.append(
                    {
                        "canonical_id": f"{SOURCE_PREFIX}:purchase-order-line:{purchase_line_number:03d}",
                        "source_system": "operion",
                        "source_id": f"purchase-order-line-{purchase_line_number:03d}",
                        "purchase_order_canonical_id": order_key,
                        "product_canonical_id": product["canonical_id"],
                        "description": product["name"],
                        "source_uom": product["uom"],
                        "canonical_uom": product["uom"],
                        "units_per_outer": "1",
                        "ordered_outers": str(quantity),
                        "received_outers": str(received),
                        "open_quantity": str(quantity - received),
                        "expected_unit_price_per_outer": _money(rate),
                        "expected_unit_price_each": _money(rate),
                        "net_amount": _money(amount),
                        "currency": "EUR",
                        "last_receipt_date": required.isoformat()
                        if status == "completed"
                        else "",
                        **common,
                    }
                )
                purchase_line_number += 1
            purchase_orders.append(
                {
                    "canonical_id": order_key,
                    "source_system": "operion",
                    "source_id": f"purchase-order-{purchase_number:03d}",
                    "supplier_canonical_id": supplier_key,
                    "contact_canonical_id": contact_by_org[supplier_key],
                    "order_date": order_date.isoformat(),
                    "expected_delivery_date": required.isoformat(),
                    "supplier_reference": f"DEMO-PO-{purchase_number:03d}",
                    "source_status": status,
                    "docstatus": docstatus,
                    "business_status": status,
                    "currency": "EUR",
                    "net_total_ex_tax": _money(total),
                    **common,
                }
            )
            purchase_number += 1

    return {
        "organizations": organizations,
        "contacts": contacts,
        "products": products,
        "sales_orders": sales_orders,
        "sales_order_lines": sales_lines,
        "purchase_orders": purchase_orders,
        "purchase_order_lines": purchase_lines,
        "fulfillment_scenarios": [],
    }


def _identity_rows(
    data: dict[str, list[dict[str, Any]]],
    *,
    source_system: str = "operion",
    dataset_version: str = DATASET_VERSION,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    kinds = {
        "organizations": "organization",
        "contacts": "contact",
        "products": "product",
        "sales_orders": "sales_order",
        "sales_order_lines": "sales_order_line",
        "purchase_orders": "purchase_order",
        "purchase_order_lines": "purchase_order_line",
    }
    for filename, entity_type in kinds.items():
        for record in data[filename]:
            targets = ("erpnext",)
            if filename == "organizations" and record["roles"] == "customer":
                targets = ("erpnext", "twenty")
            elif (
                filename == "contacts"
                and ":customer:" in record["company_canonical_id"]
            ):
                targets = ("erpnext", "twenty")
            for target in targets:
                rows.append(
                    {
                        "entity_type": entity_type,
                        "source_system": source_system,
                        "source_id": str(record["source_id"]),
                        "canonical_id": str(record["canonical_id"]),
                        "target_system": target,
                        "target_id": "",
                        "batch_id": dataset_version,
                        "mapping_version": dataset_version,
                        "load_status": "pending",
                        "error": "",
                    }
                )
    return rows


def prepare_interview_demo(
    output_directory: Path,
    identity_map: Path,
    *,
    business_date: date = DEFAULT_BUSINESS_DATE,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    data = build_interview_demo(business_date, seed)
    for filename, rows in data.items():
        _write_csv(output_directory / f"{filename}.csv", rows)
    identity_rows = _identity_rows(data)
    identity_map.parent.mkdir(parents=True, exist_ok=True)
    with identity_map.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=IDENTITY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(identity_rows)
    manifest = {
        "dataset_version": DATASET_VERSION,
        "source_system": "operion",
        "data_class": "simulated",
        "seed": seed,
        "business_date": business_date.isoformat(),
        "source_observed_at": None,
        "currency": "EUR",
        "amount_basis": "tax_exclusive",
        "counts": {name: len(rows) for name, rows in data.items()},
        "identity_rows": len(identity_rows),
    }
    manifest_path = output_directory / "dataset.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_interview_demo(directory: Path) -> dict[str, Any]:
    data: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    for filename in FILE_FIELDS:
        path = directory / f"{filename}.csv"
        try:
            with path.open(encoding="utf-8", newline="") as stream:
                data[filename] = list(csv.DictReader(stream))
        except OSError:
            errors.append(f"missing file: {path.name}")
            data[filename] = []
    expected_counts = {
        "organizations": 15,
        "contacts": 20,
        "products": 12,
        "sales_orders": 30,
        "purchase_orders": 15,
    }
    for name, expected in expected_counts.items():
        if len(data[name]) != expected:
            errors.append(f"{name}: expected {expected}, got {len(data[name])}")
    ids = {
        name: {row["canonical_id"] for row in rows}
        for name, rows in data.items()
        if name != "fulfillment_scenarios"
    }
    for row in data["contacts"]:
        if row["company_canonical_id"] not in ids["organizations"]:
            errors.append(f"contact has missing organization: {row['canonical_id']}")
    for row in data["sales_orders"]:
        if row["customer_canonical_id"] not in ids["organizations"]:
            errors.append(f"sales order has missing customer: {row['canonical_id']}")
    for row in data["purchase_orders"]:
        if row["supplier_canonical_id"] not in ids["organizations"]:
            errors.append(f"purchase order has missing supplier: {row['canonical_id']}")
    for filename, parent_field, parent_table in (
        ("sales_order_lines", "sales_order_canonical_id", "sales_orders"),
        ("purchase_order_lines", "purchase_order_canonical_id", "purchase_orders"),
    ):
        for row in data[filename]:
            if row[parent_field] not in ids[parent_table]:
                errors.append(f"line has missing order: {row['canonical_id']}")
            if row["product_canonical_id"] not in ids["products"]:
                errors.append(f"line has missing product: {row['canonical_id']}")
    sales_by_customer = Counter(
        row["customer_canonical_id"] for row in data["sales_orders"]
    )
    purchase_by_supplier = Counter(
        row["supplier_canonical_id"] for row in data["purchase_orders"]
    )
    if 0 not in [
        sales_by_customer.get(f"{SOURCE_PREFIX}:customer:{i:03d}", 0)
        for i in range(1, 11)
    ]:
        errors.append("no zero-sales-order customer")
    if 0 not in [
        purchase_by_supplier.get(f"{SOURCE_PREFIX}:supplier:{i:03d}", 0)
        for i in range(1, 6)
    ]:
        errors.append("no zero-purchase-order supplier")
    if max(sales_by_customer.values(), default=0) < 8:
        errors.append("no customer has at least eight sales orders")
    for order_table, line_table, relation in (
        ("sales_orders", "sales_order_lines", "sales_order_canonical_id"),
        ("purchase_orders", "purchase_order_lines", "purchase_order_canonical_id"),
    ):
        by_order: dict[str, Decimal] = Counter()
        for row in data[line_table]:
            by_order[row[relation]] += Decimal(row["net_amount"])
        for row in data[order_table]:
            if by_order[row["canonical_id"]] != Decimal(row["net_total_ex_tax"]):
                errors.append(f"amount mismatch: {row['canonical_id']}")
    return {
        "status": "passed" if not errors else "failed",
        "dataset_version": DATASET_VERSION,
        "counts": {name: len(rows) for name, rows in data.items()},
        "errors": errors,
    }


def provision_plan(
    directory: Path,
    *,
    validator: Callable[[Path], dict[str, Any]] = validate_interview_demo,
    dataset_version: str = DATASET_VERSION,
) -> dict[str, Any]:
    validation = validator(directory)
    if validation["status"] != "passed":
        return {"status": "blocked", "validation": validation}
    data = _load_directory(directory)
    customer_ids = {
        row["canonical_id"]
        for row in data["organizations"]
        if row["roles"] == "customer"
    }
    customer_contacts = sum(
        row["company_canonical_id"] in customer_ids for row in data["contacts"]
    )
    customers = len(customer_ids)
    suppliers = len(data["organizations"]) - customers
    return {
        "status": "dry_run",
        "dataset_version": dataset_version,
        "operations": [
            {
                "system": "ERPNext",
                "objects": (
                    f"{customers} Customer, {suppliers} Supplier, "
                    f"{len(data['products'])} Item, {len(data['contacts'])} Contact, "
                    f"{len(data['sales_orders'])} Sales Order, "
                    f"{len(data['purchase_orders'])} Purchase Order"
                ),
            },
            {
                "system": "Twenty",
                "objects": (
                    f"{customers} Company, {customer_contacts} customer-linked Person"
                ),
            },
        ],
        "dependencies": [
            "masters before contacts",
            "masters and items before orders",
            "stable source-key readback before identity-map update",
        ],
        "side_effects": [
            "creates draft documents",
            "does not create invoices, payments, deliveries, receipts, or stock entries",
            "does not submit orders unless a future separately-reviewed workflow explicitly allows it",
        ],
        "apply_requirements": [
            "dedicated admin env file",
            "OPERION_DEMO_INSTANCE=1",
            "OPERION_DEMO_BACKUP_CONFIRMED=1",
            "OPERION_DEMO_EXTERNAL_EFFECTS_DISABLED=1",
            "explicit exchange-rate env when dataset and company currencies differ",
        ],
        "validation": validation,
    }


ERP_SOURCE_FIELDS = {
    "Customer": "custom_operion_source_key",
    "Supplier": "custom_operion_sourcekey",
    "Item": "custom_operion_source_key",
    "Contact": "custom_operion_source_key",
    "Sales Order": "custom_operion_source_key",
    "Purchase Order": "custom_operion_source_key",
}
UOM_MAP = {
    "Each": "Unit",
    "Unit": "Unit",
    "Roll": "Roll",
    "Kilogram": "Kg",
    "Pack": "Pack",
}


def _load_directory(directory: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for name in FILE_FIELDS:
        with (directory / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
            result[name] = list(csv.DictReader(stream))
    return result


def _assert_apply_preflight(values: dict[str, str]) -> None:
    required_flags = (
        "OPERION_DEMO_INSTANCE",
        "OPERION_DEMO_BACKUP_CONFIRMED",
        "OPERION_DEMO_EXTERNAL_EFFECTS_DISABLED",
    )
    missing = [key for key in required_flags if values.get(key) != "1"]
    backup = Path(values.get("OPERION_DEMO_BACKUP_PATH", ""))
    if missing:
        raise RuntimeError(
            f"apply blocked; required safeguards are not attested: {missing}"
        )
    if not values.get("OPERION_DEMO_RESTORE_COMMAND", "").strip():
        raise RuntimeError("apply blocked; OPERION_DEMO_RESTORE_COMMAND is required")
    if not backup.is_file():
        raise RuntimeError("apply blocked; OPERION_DEMO_BACKUP_PATH is not a file")
    for key in ("TWENTY_API_KEY", "ERPNEXT_API_KEY"):
        if not values.get(key, "").strip():
            raise RuntimeError(f"apply blocked; {key} is missing from the admin env")


def _create_or_confirm(
    client: ERPNextAdminClient,
    doctype: str,
    source_key: str,
    expected_name_field: str,
    expected_name: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    source_field = ERP_SOURCE_FIELDS[doctype]
    current = _find_one(client, doctype, source_field, source_key)
    if current is not None:
        detail = client.get(doctype, current["name"])
        if str(detail.get(expected_name_field) or "") != expected_name:
            raise RuntimeError(
                f"conflict for {doctype} {source_key}: target was manually changed"
            )
        return detail, "existing"
    return client.create(doctype, payload), "created"


def apply_interview_demo(
    directory: Path,
    identity_map: Path,
    admin_env: Path,
    *,
    validator: Callable[[Path], dict[str, Any]] = validate_interview_demo,
    dataset_version: str = DATASET_VERSION,
) -> dict[str, Any]:
    """Create only missing demo objects; orders remain draft and are never submitted."""
    validation = validator(directory)
    if validation["status"] != "passed":
        raise RuntimeError(f"apply blocked; validation failed: {validation['errors']}")
    values = read_env(admin_env)
    _assert_apply_preflight(values)
    data = _load_directory(directory)
    company_currency = values.get("OPERION_COMPANY_CURRENCY", "EUR")
    dataset_currencies = {
        row["currency"]
        for table in ("products", "sales_orders", "purchase_orders")
        for row in data[table]
        if row.get("currency")
    }
    exchange_rates: dict[str, Decimal] = {company_currency: Decimal("1")}
    for currency in sorted(dataset_currencies - {company_currency}):
        key = f"OPERION_DEMO_EXCHANGE_RATE_{currency}_TO_{company_currency}"
        try:
            rate = Decimal(values.get(key, ""))
        except Exception as error:
            raise RuntimeError(
                f"apply blocked; valid positive {key} is required"
            ) from error
        if rate <= 0:
            raise RuntimeError(f"apply blocked; valid positive {key} is required")
        exchange_rates[currency] = rate
    erp = ERPNextAdminClient(
        values.get("ERPNEXT_API_BASE_URL", "http://localhost:8080"),
        values["ERPNEXT_API_KEY"],
    )
    twenty = TwentyClient(
        values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
        values["TWENTY_API_KEY"],
    )
    # Complete all read-only schema/dependency checks before the first write.
    twenty_companies = twenty.companies()
    twenty_people = twenty.people()
    available_uoms = {row["name"] for row in erp.list("UOM", ["name"])}
    missing_uoms = sorted(set(UOM_MAP.values()) - available_uoms)
    if missing_uoms:
        raise RuntimeError(f"apply blocked; ERPNext UOMs are missing: {missing_uoms}")
    required_custom_fields = {
        ("Customer", "custom_operion_source_key"),
        ("Supplier", "custom_operion_sourcekey"),
        ("Item", "custom_operion_source_key"),
        ("Contact", "custom_operion_source_key"),
        ("Sales Order", "custom_operion_source_key"),
        ("Sales Order Item", "custom_operion_source_key_items"),
        ("Purchase Order", "custom_operion_source_key"),
        ("Purchase Order Item", "custom_operion_source_key"),
    }
    installed_custom_fields = {
        (str(row.get("dt") or ""), str(row.get("fieldname") or ""))
        for row in erp.list("Custom Field", ["name", "dt", "fieldname"])
    }
    missing_fields = sorted(required_custom_fields - installed_custom_fields)
    if missing_fields:
        raise RuntimeError(
            f"apply blocked; required ERPNext source-key fields are missing: {missing_fields}"
        )
    dependencies = {
        "Company": values.get("OPERION_COMPANY", "AI Demo GmbH"),
        "Customer Group": values.get("OPERION_DEMO_CUSTOMER_GROUP", "Commercial"),
        "Territory": values.get("OPERION_DEMO_TERRITORY", "Germany"),
        "Supplier Group": values.get(
            "OPERION_DEMO_SUPPLIER_GROUP", "All Supplier Groups"
        ),
        "Item Group": values.get("OPERION_DEMO_ITEM_GROUP", "Products"),
        "Price List": values.get("OPERION_DEMO_SELLING_PRICE_LIST", "Standard Selling"),
    }
    missing_dependencies = [
        f"{doctype}:{name}"
        for doctype, name in dependencies.items()
        if not erp.list(doctype, ["name"], [["name", "=", name]])
    ]
    buying_price_list = values.get("OPERION_DEMO_BUYING_PRICE_LIST", "Standard Buying")
    if not erp.list("Price List", ["name"], [["name", "=", buying_price_list]]):
        missing_dependencies.append(f"Price List:{buying_price_list}")
    if missing_dependencies:
        raise RuntimeError(
            f"apply blocked; ERPNext dependencies are missing: {missing_dependencies}"
        )
    counts: Counter[str] = Counter()
    target_ids: dict[tuple[str, str], str] = {}
    erp_names: dict[str, str] = {}

    for row in data["organizations"]:
        if row["roles"] == "customer":
            doctype, name_field = "Customer", "customer_name"
            payload = {
                "customer_name": row["name"],
                "customer_type": "Company",
                "customer_group": values.get(
                    "OPERION_DEMO_CUSTOMER_GROUP", "Commercial"
                ),
                "territory": values.get("OPERION_DEMO_TERRITORY", "Germany"),
                ERP_SOURCE_FIELDS["Customer"]: row["canonical_id"],
            }
        else:
            doctype, name_field = "Supplier", "supplier_name"
            payload = {
                "supplier_name": row["name"],
                "supplier_type": "Company",
                "supplier_group": values.get(
                    "OPERION_DEMO_SUPPLIER_GROUP", "All Supplier Groups"
                ),
                ERP_SOURCE_FIELDS["Supplier"]: row["canonical_id"],
            }
        doc, outcome = _create_or_confirm(
            erp, doctype, row["canonical_id"], name_field, row["name"], payload
        )
        counts[f"erpnext_{outcome}"] += 1
        erp_names[row["canonical_id"]] = doc["name"]
        target_ids[("erpnext", row["canonical_id"])] = doc["name"]

    for row in data["products"]:
        product_currency = row.get("currency") or company_currency
        payload = {
            "item_code": row["canonical_id"],
            "item_name": row["name"],
            "item_group": values.get("OPERION_DEMO_ITEM_GROUP", "Products"),
            "stock_uom": UOM_MAP[row["uom"]],
            "is_stock_item": 0,
            "standard_rate": str(
                Decimal(row["unit_price_ex_tax"]) * exchange_rates[product_currency]
            ),
            ERP_SOURCE_FIELDS["Item"]: row["canonical_id"],
        }
        doc, outcome = _create_or_confirm(
            erp, "Item", row["canonical_id"], "item_name", row["name"], payload
        )
        counts[f"erpnext_{outcome}"] += 1
        erp_names[row["canonical_id"]] = doc["name"]
        target_ids[("erpnext", row["canonical_id"])] = doc["name"]

    for row in data["contacts"]:
        first, _, last = row["full_name"].partition(" ")
        company_id = row["company_canonical_id"]
        payload = {
            "first_name": first,
            "last_name": last,
            ERP_SOURCE_FIELDS["Contact"]: row["canonical_id"],
            "links": (
                [
                    {
                        "link_doctype": (
                            "Customer" if ":customer:" in company_id else "Supplier"
                        ),
                        "link_name": erp_names[company_id],
                    }
                ]
                if company_id
                else []
            ),
        }
        doc, outcome = _create_or_confirm(
            erp,
            "Contact",
            row["canonical_id"],
            "first_name",
            first,
            payload,
        )
        counts[f"erpnext_{outcome}"] += 1
        target_ids[("erpnext", row["canonical_id"])] = doc["name"]

    sales_lines: dict[str, list[dict[str, str]]] = {}
    for row in data["sales_order_lines"]:
        sales_lines.setdefault(row["sales_order_canonical_id"], []).append(row)
    for row in data["sales_orders"]:
        order_currency = row.get("currency") or company_currency
        payload = {
            "customer": erp_names[row["customer_canonical_id"]],
            "company": values.get("OPERION_COMPANY", "AI Demo GmbH"),
            "transaction_date": row["order_date"],
            "delivery_date": row["expected_delivery_date"],
            "currency": order_currency,
            "conversion_rate": str(exchange_rates[order_currency]),
            "selling_price_list": values.get(
                "OPERION_DEMO_SELLING_PRICE_LIST", "Standard Selling"
            ),
            "po_no": row["customer_po_number"],
            ERP_SOURCE_FIELDS["Sales Order"]: row["canonical_id"],
            "items": [
                {
                    "item_code": erp_names[item["product_canonical_id"]],
                    "delivery_date": row["expected_delivery_date"],
                    "qty": item["ordered_quantity"],
                    "uom": UOM_MAP[item["uom"]],
                    "conversion_factor": 1,
                    "rate": item["unit_price_ex_tax"],
                    "custom_operion_source_key_items": item["canonical_id"],
                }
                for item in sales_lines[row["canonical_id"]]
            ],
        }
        doc, outcome = _create_or_confirm(
            erp,
            "Sales Order",
            row["canonical_id"],
            "po_no",
            row["customer_po_number"],
            payload,
        )
        if int(doc.get("docstatus") or 0) != 0:
            raise RuntimeError(f"conflict: demo Sales Order {doc['name']} is not draft")
        counts[f"erpnext_{outcome}"] += 1
        target_ids[("erpnext", row["canonical_id"])] = doc["name"]
        for item in doc.get("items", []):
            key = str(item.get("custom_operion_source_key_items") or "")
            if key:
                target_ids[("erpnext", key)] = item["name"]

    purchase_lines: dict[str, list[dict[str, str]]] = {}
    for row in data["purchase_order_lines"]:
        purchase_lines.setdefault(row["purchase_order_canonical_id"], []).append(row)
    for row in data["purchase_orders"]:
        order_currency = row.get("currency") or company_currency
        payload = {
            "supplier": erp_names[row["supplier_canonical_id"]],
            "company": values.get("OPERION_COMPANY", "AI Demo GmbH"),
            "transaction_date": row["order_date"],
            "schedule_date": row["expected_delivery_date"],
            "currency": order_currency,
            "conversion_rate": str(exchange_rates[order_currency]),
            "buying_price_list": values.get(
                "OPERION_DEMO_BUYING_PRICE_LIST", "Standard Buying"
            ),
            ERP_SOURCE_FIELDS["Purchase Order"]: row["canonical_id"],
            "items": [
                {
                    "item_code": erp_names[item["product_canonical_id"]],
                    "schedule_date": row["expected_delivery_date"],
                    "qty": item["ordered_outers"],
                    "uom": UOM_MAP[item["canonical_uom"]],
                    "conversion_factor": 1,
                    "rate": item["expected_unit_price_each"],
                    "custom_operion_source_key": item["canonical_id"],
                }
                for item in purchase_lines[row["canonical_id"]]
            ],
        }
        doc, outcome = _create_or_confirm(
            erp,
            "Purchase Order",
            row["canonical_id"],
            "supplier",
            erp_names[row["supplier_canonical_id"]],
            payload,
        )
        if int(doc.get("docstatus") or 0) != 0:
            raise RuntimeError(
                f"conflict: demo Purchase Order {doc['name']} is not draft"
            )
        counts[f"erpnext_{outcome}"] += 1
        target_ids[("erpnext", row["canonical_id"])] = doc["name"]
        for item in doc.get("items", []):
            key = str(item.get("custom_operion_source_key") or "")
            if key:
                target_ids[("erpnext", key)] = item["name"]

    companies = {row.get("wwiExternalId", ""): row for row in twenty_companies}
    company_ids: dict[str, str] = {}
    for row in data["organizations"]:
        if row["roles"] != "customer":
            continue
        current = companies.get(row["canonical_id"])
        if current:
            if current.get("name") != row["name"]:
                raise RuntimeError(
                    f"conflict for Twenty Company {row['canonical_id']}: name changed"
                )
            company = current
            counts["twenty_existing"] += 1
        else:
            company = twenty.create_company(
                {"name": row["name"], "wwiExternalId": row["canonical_id"]}
            )
            counts["twenty_created"] += 1
        company_ids[row["canonical_id"]] = company["id"]
        target_ids[("twenty", row["canonical_id"])] = company["id"]

    people = {row.get("wwiExternalId", ""): row for row in twenty_people}
    for row in data["contacts"]:
        if row["company_canonical_id"] not in company_ids:
            continue
        first, _, last = row["full_name"].partition(" ")
        current = people.get(row["canonical_id"])
        if current:
            name = current.get("name") or {}
            if name.get("firstName") != first or name.get("lastName") != last:
                raise RuntimeError(
                    f"conflict for Twenty Person {row['canonical_id']}: name changed"
                )
            person = current
            counts["twenty_existing"] += 1
        else:
            person = twenty.create_person(
                {
                    "name": {"firstName": first, "lastName": last},
                    "companyId": company_ids[row["company_canonical_id"]],
                    "wwiExternalId": row["canonical_id"],
                }
            )
            counts["twenty_created"] += 1
        target_ids[("twenty", row["canonical_id"])] = person["id"]

    with identity_map.open(encoding="utf-8", newline="") as stream:
        identity_rows = list(csv.DictReader(stream))
    for row in identity_rows:
        target = target_ids.get((row["target_system"], row["canonical_id"]))
        if target:
            row["target_id"] = target
            row["load_status"] = "loaded"
            row["error"] = ""
    with identity_map.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=IDENTITY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(identity_rows)
    return {
        "status": "applied_and_read_back",
        "dataset_version": dataset_version,
        "counts": dict(counts),
        "identity_rows_loaded": sum(
            row["load_status"] == "loaded" for row in identity_rows
        ),
        "orders_submitted": 0,
    }
