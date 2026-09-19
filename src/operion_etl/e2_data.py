from __future__ import annotations

import csv
import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .identity_readback import IDENTITY_FIELDS
from .twenty import TwentyClient, read_env

E2_BATCH_ID = "operion-e2-demo-v1"
E2_CUSTOMER_NAME = "Operion E2 Ambiguous Customer"
E2_CUSTOMERS = (
    {
        "canonical_id": "operion:e2:organization:customer:ambiguous-a",
        "source_id": "ambiguous-a",
        "contact_id": "operion:e2:contact:ambiguous-a",
        "contact_source_id": "ambiguous-a",
        "contact_first_name": "Alex",
        "contact_last_name": "Example",
    },
    {
        "canonical_id": "operion:e2:organization:customer:ambiguous-b",
        "source_id": "ambiguous-b",
        "contact_id": "operion:e2:contact:ambiguous-b",
        "contact_source_id": "ambiguous-b",
        "contact_first_name": "Blair",
        "contact_last_name": "Example",
    },
)

E2_FULFILLMENT = {
    "F01": {"product": "wwi:product:77", "ordered": "108", "delivered": "0"},
    "F02": {"product": "wwi:product:193", "ordered": "72", "delivered": "0"},
    "F03": {"product": "wwi:product:78", "ordered": "96", "delivered": "0"},
    "F04": {"product": "wwi:product:80", "ordered": "36", "delivered": "0"},
    "F05": {"product": "wwi:product:98", "ordered": "48", "delivered": "24"},
    "F06": {"product": "wwi:product:204", "ordered": "90", "delivered": "0"},
}

E2_PURCHASES = {
    "F02": {
        "supplier": "wwi:organization:supplier:4",
        "contact": "wwi:contact:2",
        "product": "wwi:product:193",
        "quantity": "2",
        "date": "2016-06-02",
    },
    "F03": {
        "supplier": "wwi:organization:supplier:7",
        "contact": "wwi:contact:2",
        "product": "wwi:product:78",
        "quantity": "2",
        "date": "2016-06-04",
    },
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _append_unique(
    rows: list[dict[str, str]], additions: list[dict[str, str]], key: str
) -> None:
    additions_by_key = {row[key]: row for row in additions}
    rows[:] = [row for row in rows if row.get(key) not in additions_by_key]
    rows.extend(additions)


def _identity_row(
    *,
    entity_type: str,
    source_id: str,
    canonical_id: str,
    target_system: str,
) -> dict[str, str]:
    return {
        "entity_type": entity_type,
        "source_system": "operion",
        "source_id": source_id,
        "canonical_id": canonical_id,
        "target_system": target_system,
        "target_id": "",
        "batch_id": E2_BATCH_ID,
        "mapping_version": "operion-e2-demo-v1",
        "load_status": "pending",
        "error": "",
    }


def prepare_e2_batch(
    base_directory: Path,
    base_identity_map: Path,
    output_directory: Path,
    output_identity_map: Path,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    for source in base_directory.glob("*.csv"):
        shutil.copy2(source, output_directory / source.name)

    fields, organizations = _read_csv(output_directory / "organizations.csv")
    organization_rows = [
        {
            "canonical_id": spec["canonical_id"],
            "source_system": "operion",
            "source_id": spec["source_id"],
            "name": E2_CUSTOMER_NAME,
            "roles": "customer",
            "primary_contact_source_id": spec["contact_source_id"],
            "phone": "",
            "website": "",
            "address_line_1": "Evaluation fixture",
            "address_line_2": "",
            "city": "Berlin",
            "state": "Berlin",
            "country": "Germany",
            "postal_code": "10115",
            "payment_days": "0",
            "credit_limit": "0",
            "created_at": "2016-05-31",
            "updated_at": "2016-05-31T00:00:00",
            "data_class": "simulated",
        }
        for spec in E2_CUSTOMERS
    ]
    _append_unique(organizations, organization_rows, "canonical_id")
    _write_csv(output_directory / "organizations.csv", fields, organizations)

    fields, contacts = _read_csv(output_directory / "contacts.csv")
    contact_rows = [
        {
            "canonical_id": spec["contact_id"],
            "source_system": "operion",
            "source_id": spec["contact_source_id"],
            "full_name": (f"{spec['contact_first_name']} {spec['contact_last_name']}"),
            "preferred_name": spec["contact_first_name"],
            "email": "",
            "phone": "",
            "company_canonical_id": spec["canonical_id"],
            "is_employee": "false",
            "is_salesperson": "false",
            "data_class": "simulated",
        }
        for spec in E2_CUSTOMERS
    ]
    _append_unique(contacts, contact_rows, "canonical_id")
    _write_csv(output_directory / "contacts.csv", fields, contacts)

    _, products = _read_csv(output_directory / "products.csv")
    product_names = {row["canonical_id"]: row["name"] for row in products}
    customer = E2_CUSTOMERS[0]

    fields, sales_orders = _read_csv(output_directory / "sales_orders.csv")
    sales_order_rows = []
    for case_id in E2_FULFILLMENT:
        sales_order_rows.append(
            {
                "canonical_id": f"operion:e2:sales_order:{case_id}",
                "source_system": "operion",
                "source_id": case_id,
                "customer_canonical_id": customer["canonical_id"],
                "contact_canonical_id": customer["contact_id"],
                "salesperson_canonical_id": "",
                "order_date": "2016-05-31",
                "expected_delivery_date": "2016-06-03",
                "customer_po_number": f"E2-{case_id}",
                "source_status": "open",
                "data_class": "simulated",
            }
        )
    sales_order_rows.append(
        {
            "canonical_id": "operion:e2:sales_order:F04-reservation",
            "source_system": "operion",
            "source_id": "F04-reservation",
            "customer_canonical_id": customer["canonical_id"],
            "contact_canonical_id": customer["contact_id"],
            "salesperson_canonical_id": "",
            "order_date": "2016-05-31",
            "expected_delivery_date": "2016-06-03",
            "customer_po_number": "E2-F04-RESERVE",
            "source_status": "open",
            "data_class": "simulated",
        }
    )
    _append_unique(sales_orders, sales_order_rows, "canonical_id")
    _write_csv(output_directory / "sales_orders.csv", fields, sales_orders)

    fields, sales_lines = _read_csv(output_directory / "sales_order_lines.csv")
    sales_line_rows = []
    for case_id, spec in E2_FULFILLMENT.items():
        ordered = int(spec["ordered"])
        delivered = int(spec["delivered"])
        sales_line_rows.append(
            {
                "canonical_id": f"operion:e2:sales_order_line:{case_id}",
                "source_system": "operion",
                "source_id": case_id,
                "sales_order_canonical_id": f"operion:e2:sales_order:{case_id}",
                "product_canonical_id": spec["product"],
                "description": product_names[spec["product"]],
                "uom": "Each",
                "ordered_quantity": spec["ordered"],
                "delivered_quantity": spec["delivered"],
                "open_quantity": str(ordered - delivered),
                "unit_price_ex_tax": "1.00",
                "tax_rate_percent": "0",
                "net_amount": f"{ordered:.2f}",
                "data_class": "simulated",
            }
        )
    sales_line_rows.append(
        {
            "canonical_id": "operion:e2:sales_order_line:F04-reservation",
            "source_system": "operion",
            "source_id": "F04-reservation",
            "sales_order_canonical_id": "operion:e2:sales_order:F04-reservation",
            "product_canonical_id": "wwi:product:80",
            "description": product_names["wwi:product:80"],
            "uom": "Each",
            "ordered_quantity": "1",
            "delivered_quantity": "0",
            "open_quantity": "1",
            "unit_price_ex_tax": "1.00",
            "tax_rate_percent": "0",
            "net_amount": "1.00",
            "data_class": "simulated",
        }
    )
    _append_unique(sales_lines, sales_line_rows, "canonical_id")
    _write_csv(output_directory / "sales_order_lines.csv", fields, sales_lines)

    fields, purchase_orders = _read_csv(output_directory / "purchase_orders.csv")
    purchase_order_rows = []
    for case_id, spec in E2_PURCHASES.items():
        purchase_order_rows.append(
            {
                "canonical_id": f"operion:e2:purchase_order:{case_id}",
                "source_system": "operion",
                "source_id": case_id,
                "supplier_canonical_id": spec["supplier"],
                "contact_canonical_id": spec["contact"],
                "order_date": "2016-05-31",
                "expected_delivery_date": spec["date"],
                "supplier_reference": f"E2-{case_id}",
                "source_status": "open",
                "data_class": "simulated",
            }
        )
    _append_unique(purchase_orders, purchase_order_rows, "canonical_id")
    _write_csv(output_directory / "purchase_orders.csv", fields, purchase_orders)

    fields, purchase_lines = _read_csv(output_directory / "purchase_order_lines.csv")
    purchase_line_rows = []
    for case_id, spec in E2_PURCHASES.items():
        purchase_line_rows.append(
            {
                "canonical_id": f"operion:e2:purchase_order_line:{case_id}",
                "source_system": "operion",
                "source_id": case_id,
                "purchase_order_canonical_id": (f"operion:e2:purchase_order:{case_id}"),
                "product_canonical_id": spec["product"],
                "description": product_names[spec["product"]],
                "source_uom": "Each",
                "canonical_uom": "Each",
                "units_per_outer": "1",
                "ordered_outers": spec["quantity"],
                "received_outers": "0",
                "open_quantity": spec["quantity"],
                "expected_unit_price_per_outer": "1.00",
                "expected_unit_price_each": "1.00",
                "last_receipt_date": "",
                "data_class": "simulated",
            }
        )
    _append_unique(purchase_lines, purchase_line_rows, "canonical_id")
    _write_csv(output_directory / "purchase_order_lines.csv", fields, purchase_lines)

    fields, scenarios = _read_csv(output_directory / "fulfillment_scenarios.csv")
    evidence_fields = [
        "on_hand_source",
        "reservation_source",
        "inbound_source",
        "fulfillment_source",
    ]
    for field in evidence_fields:
        if field not in fields:
            fields.append(field)
    for scenario in scenarios:
        case_id = scenario["case_id"]
        spec = E2_FULFILLMENT[case_id]
        scenario["derived_from"] = f"operion:e2:sales_order_line:{case_id}"
        scenario["product_canonical_id"] = spec["product"]
        scenario["on_hand_source"] = "operion:e2:stock_entry:opening"
        scenario["reservation_source"] = (
            "operion:e2:sales_order_line:F04-reservation" if case_id == "F04" else ""
        )
        scenario["inbound_source"] = (
            f"operion:e2:purchase_order_line:{case_id}"
            if case_id in E2_PURCHASES
            else ("operion:e2:missing_inbound:F06" if case_id == "F06" else "")
        )
        scenario["fulfillment_source"] = (
            "operion:e2:delivery_note:F05" if case_id == "F05" else ""
        )
    _write_csv(output_directory / "fulfillment_scenarios.csv", fields, scenarios)

    _, identity_rows = _read_csv(base_identity_map)
    for row in identity_rows:
        row["batch_id"] = E2_BATCH_ID
    additions: list[dict[str, str]] = []
    for spec in E2_CUSTOMERS:
        for target in ("erpnext", "twenty"):
            additions.append(
                _identity_row(
                    entity_type="organization",
                    source_id=spec["source_id"],
                    canonical_id=spec["canonical_id"],
                    target_system=target,
                )
            )
            additions.append(
                _identity_row(
                    entity_type="contact",
                    source_id=spec["contact_source_id"],
                    canonical_id=spec["contact_id"],
                    target_system=target,
                )
            )
    for row in [*sales_order_rows, *purchase_order_rows]:
        entity_type = (
            "sales_order"
            if ":sales_order:" in row["canonical_id"]
            else "purchase_order"
        )
        additions.append(
            _identity_row(
                entity_type=entity_type,
                source_id=row["source_id"],
                canonical_id=row["canonical_id"],
                target_system="erpnext",
            )
        )
    for row in [*sales_line_rows, *purchase_line_rows]:
        entity_type = (
            "sales_order_line"
            if ":sales_order_line:" in row["canonical_id"]
            else "purchase_order_line"
        )
        additions.append(
            _identity_row(
                entity_type=entity_type,
                source_id=row["source_id"],
                canonical_id=row["canonical_id"],
                target_system="erpnext",
            )
        )
    addition_keys = {(row["canonical_id"], row["target_system"]) for row in additions}
    identity_rows = [
        row
        for row in identity_rows
        if (row["canonical_id"], row["target_system"]) not in addition_keys
    ]
    identity_rows.extend(additions)
    # Canonical IDs can legitimately have one row per target system.
    identity_index = {
        (row["canonical_id"], row["target_system"]): row for row in identity_rows
    }
    _write_csv(output_identity_map, IDENTITY_FIELDS, list(identity_index.values()))
    return {
        "status": "prepared",
        "batch_id": E2_BATCH_ID,
        "canonical_directory": str(output_directory),
        "identity_map": str(output_identity_map),
        "added": {
            "customers": len(organization_rows),
            "contacts": len(contact_rows),
            "sales_orders": len(sales_order_rows),
            "sales_order_lines": len(sales_line_rows),
            "purchase_orders": len(purchase_order_rows),
            "purchase_order_lines": len(purchase_line_rows),
        },
    }


class ERPNextAdminClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=self.headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.load(response) if response.length != 0 else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(
                f"ERPNext {method} {path} failed with HTTP {error.code}: "
                f"{detail[:1200]}"
            ) from error

    def list(
        self,
        doctype: str,
        fields: list[str],
        filters: list[list[Any]] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "fields": json.dumps(fields, separators=(",", ":")),
            "limit_page_length": 500,
        }
        if filters:
            params["filters"] = json.dumps(filters, separators=(",", ":"))
        path = "/api/resource/{}?{}".format(
            urllib.parse.quote(doctype, safe=""), urllib.parse.urlencode(params)
        )
        return self.request("GET", path).get("data", [])

    def get(self, doctype: str, name: str) -> dict[str, Any]:
        path = "/api/resource/{}/{}".format(
            urllib.parse.quote(doctype, safe=""),
            urllib.parse.quote(name, safe=""),
        )
        return self.request("GET", path)["data"]

    def create(self, doctype: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = "/api/resource/" + urllib.parse.quote(doctype, safe="")
        return self.request("POST", path, {"doctype": doctype, **payload})["data"]

    def update(
        self, doctype: str, name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        path = "/api/resource/{}/{}".format(
            urllib.parse.quote(doctype, safe=""),
            urllib.parse.quote(name, safe=""),
        )
        return self.request("PUT", path, payload)["data"]

    def submit(self, doctype: str, name: str) -> dict[str, Any]:
        doc = self.get(doctype, name)
        return self.request("POST", "/api/method/frappe.client.submit", {"doc": doc})[
            "message"
        ]

    def call(self, method: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", "/api/method/" + method, payload).get("message")


def _find_one(
    client: ERPNextAdminClient,
    doctype: str,
    field: str,
    value: str,
) -> dict[str, Any] | None:
    rows = client.list(doctype, ["name", "docstatus", field], [[field, "=", value]])
    if len(rows) > 1:
        raise RuntimeError(f"ambiguous {doctype} for {field}={value}")
    return rows[0] if rows else None


def _find_delivery_for_sales_order(
    client: ERPNextAdminClient, sales_order: str
) -> dict[str, Any] | None:
    matches = []
    for row in client.list("Delivery Note", ["name", "docstatus"]):
        if int(row.get("docstatus") or 0) == 2:
            continue
        detail = client.get("Delivery Note", row["name"])
        if any(
            item.get("against_sales_order") == sales_order
            for item in detail.get("items", [])
        ):
            matches.append(detail)
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous Delivery Note for Sales Order={sales_order}")
    return matches[0] if matches else None


def _ensure_submitted(
    client: ERPNextAdminClient,
    doctype: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    if int(row.get("docstatus") or 0) == 0:
        return client.submit(doctype, row["name"])
    if int(row.get("docstatus") or 0) != 1:
        raise RuntimeError(f"{doctype} {row['name']} is cancelled")
    return client.get(doctype, row["name"])


def _seed_erpnext_masters(
    client: ERPNextAdminClient,
) -> tuple[dict[str, str], dict[str, str], str, dict[str, int]]:
    selling_settings = client.get("Selling Settings", "Selling Settings")
    original_customer_naming = selling_settings.get("cust_master_name")
    missing_customers = [
        spec
        for spec in E2_CUSTOMERS
        if _find_one(
            client,
            "Customer",
            "custom_operion_source_key",
            spec["canonical_id"],
        )
        is None
    ]
    if missing_customers:
        client.update(
            "Selling Settings",
            "Selling Settings",
            {"cust_master_name": "Naming Series"},
        )
    customer_names: dict[str, str] = {}
    try:
        for spec in E2_CUSTOMERS:
            current = _find_one(
                client,
                "Customer",
                "custom_operion_source_key",
                spec["canonical_id"],
            )
            if current is None:
                current = client.create(
                    "Customer",
                    {
                        "naming_series": "CUST-.YYYY.-",
                        "customer_name": E2_CUSTOMER_NAME,
                        "customer_type": "Company",
                        "customer_group": "Commercial",
                        "territory": "Germany",
                        "custom_operion_source_key": spec["canonical_id"],
                    },
                )
            customer_names[spec["canonical_id"]] = current["name"]
    finally:
        if missing_customers:
            client.update(
                "Selling Settings",
                "Selling Settings",
                {"cust_master_name": original_customer_naming},
            )

    contact_names: dict[str, str] = {}
    for spec in E2_CUSTOMERS:
        current = _find_one(
            client,
            "Contact",
            "custom_operion_source_key",
            spec["contact_id"],
        )
        if current is None:
            current = client.create(
                "Contact",
                {
                    "first_name": spec["contact_first_name"],
                    "last_name": spec["contact_last_name"],
                    "custom_operion_source_key": spec["contact_id"],
                    "links": [
                        {
                            "link_doctype": "Customer",
                            "link_name": customer_names[spec["canonical_id"]],
                        }
                    ],
                },
            )
        contact_names[spec["contact_id"]] = current["name"]

    warehouses = client.list(
        "Warehouse",
        ["name", "warehouse_name", "company", "is_group"],
        [["warehouse_name", "=", "WWI Main Warehouse"]],
    )
    warehouse = (
        warehouses[0]
        if warehouses
        else client.create(
            "Warehouse",
            {
                "warehouse_name": "WWI Main Warehouse",
                "company": "AI Demo GmbH",
                "is_group": 0,
            },
        )
    )

    stock_settings = client.get("Stock Settings", "Stock Settings")
    settings_before = {
        "enable_stock_reservation": int(
            stock_settings.get("enable_stock_reservation") or 0
        ),
        "allow_partial_reservation": int(
            stock_settings.get("allow_partial_reservation") or 0
        ),
        "allow_negative_stock": int(stock_settings.get("allow_negative_stock") or 0),
    }
    client.update(
        "Stock Settings",
        "Stock Settings",
        {
            "enable_stock_reservation": 1,
            "allow_partial_reservation": 1,
            "allow_negative_stock": 0,
        },
    )
    return customer_names, contact_names, warehouse["name"], settings_before


def _seed_opening_stock(client: ERPNextAdminClient, warehouse: str) -> dict[str, Any]:
    marker = "operion:e2:stock_entry:opening"
    row = _find_one(client, "Stock Entry", "remarks", marker)
    if row is None:
        quantities = {
            "wwi:product:77": 113,
            "wwi:product:193": 70,
            "wwi:product:78": 94,
            "wwi:product:80": 36,
            "wwi:product:98": 48,
            "wwi:product:204": 88,
        }
        row = client.create(
            "Stock Entry",
            {
                "company": "AI Demo GmbH",
                "stock_entry_type": "Material Receipt",
                "posting_date": "2016-05-31",
                "posting_time": "08:00:00",
                "set_posting_time": 1,
                "remarks": marker,
                "items": [
                    {
                        "item_code": item_code,
                        "qty": quantity,
                        "t_warehouse": warehouse,
                        "uom": "Unit",
                        "conversion_factor": 1,
                        "basic_rate": 1,
                    }
                    for item_code, quantity in quantities.items()
                ],
            },
        )
    return _ensure_submitted(client, "Stock Entry", row)


def _sales_order_payload(
    source_key: str,
    customer: str,
    product: str,
    quantity: int,
    warehouse: str,
    *,
    reserve_stock: bool = False,
) -> dict[str, Any]:
    line_key = source_key.replace(":sales_order:", ":sales_order_line:")
    return {
        "customer": customer,
        "company": "AI Demo GmbH",
        "order_type": "Sales",
        "transaction_date": "2016-05-31",
        "delivery_date": "2016-06-03",
        "currency": "EUR",
        "conversion_rate": 1,
        "selling_price_list": "Standard Selling",
        "price_list_currency": "EUR",
        "plc_conversion_rate": 1,
        "po_no": source_key.rsplit(":", 1)[-1],
        "reserve_stock": int(reserve_stock),
        "custom_operion_source_key": source_key,
        "items": [
            {
                "item_code": product,
                "qty": quantity,
                "uom": "Unit",
                "conversion_factor": 1,
                "rate": 1,
                "warehouse": warehouse,
                "reserve_stock": int(reserve_stock),
                "custom_operion_source_key_items": line_key,
            }
        ],
    }


def _seed_sales_orders(
    client: ERPNextAdminClient,
    customer: str,
    warehouse: str,
) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for case_id, spec in E2_FULFILLMENT.items():
        source_key = f"operion:e2:sales_order:{case_id}"
        row = _find_one(client, "Sales Order", "custom_operion_source_key", source_key)
        if row is None:
            row = client.create(
                "Sales Order",
                _sales_order_payload(
                    source_key,
                    customer,
                    spec["product"],
                    int(spec["ordered"]),
                    warehouse,
                ),
            )
        documents[case_id] = _ensure_submitted(client, "Sales Order", row)

    reservation_key = "operion:e2:sales_order:F04-reservation"
    reservation = _find_one(
        client, "Sales Order", "custom_operion_source_key", reservation_key
    )
    if reservation is None:
        reservation = client.create(
            "Sales Order",
            _sales_order_payload(
                reservation_key,
                customer,
                "wwi:product:80",
                1,
                warehouse,
                reserve_stock=True,
            ),
        )
    documents["F04-reservation"] = _ensure_submitted(client, "Sales Order", reservation)
    return documents


def _seed_purchase_orders(
    client: ERPNextAdminClient,
    warehouse: str,
) -> dict[str, dict[str, Any]]:
    suppliers = {
        row["custom_operion_sourcekey"]: row["name"]
        for row in client.list(
            "Supplier",
            ["name", "custom_operion_sourcekey"],
            [
                [
                    "custom_operion_sourcekey",
                    "in",
                    [
                        "wwi:organization:supplier:4",
                        "wwi:organization:supplier:7",
                    ],
                ]
            ],
        )
    }
    documents: dict[str, dict[str, Any]] = {}
    for case_id, spec in E2_PURCHASES.items():
        source_key = f"operion:e2:purchase_order:{case_id}"
        row = _find_one(
            client, "Purchase Order", "custom_operion_source_key", source_key
        )
        if row is None:
            row = client.create(
                "Purchase Order",
                {
                    "supplier": suppliers[spec["supplier"]],
                    "transaction_date": "2016-05-31",
                    "schedule_date": spec["date"],
                    "company": "AI Demo GmbH",
                    "currency": "EUR",
                    "conversion_rate": 1,
                    "custom_operion_source_key": source_key,
                    "items": [
                        {
                            "item_code": spec["product"],
                            "schedule_date": spec["date"],
                            "qty": int(spec["quantity"]),
                            "uom": "Unit",
                            "conversion_factor": 1,
                            "rate": 1,
                            "warehouse": warehouse,
                            "custom_operion_source_key": (
                                f"operion:e2:purchase_order_line:{case_id}"
                            ),
                        }
                    ],
                },
            )
        documents[case_id] = _ensure_submitted(client, "Purchase Order", row)
    return documents


def _seed_partial_delivery(
    client: ERPNextAdminClient,
    sales_order: dict[str, Any],
) -> dict[str, Any]:
    marker = "operion:e2:delivery_note:F05"
    delivery = _find_delivery_for_sales_order(client, sales_order["name"])
    if delivery is None:
        mapped = client.call(
            "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
            {"source_name": sales_order["name"]},
        )
        mapped.pop("name", None)
        mapped["remarks"] = marker
        for item in mapped.get("items", []):
            item.pop("name", None)
            item["qty"] = 24
        delivery = client.create("Delivery Note", mapped)
    return _ensure_submitted(client, "Delivery Note", delivery)


def _update_erpnext_identities(
    identity_rows: list[dict[str, str]],
    customer_names: dict[str, str],
    contact_names: dict[str, str],
    sales_documents: dict[str, dict[str, Any]],
    purchase_documents: dict[str, dict[str, Any]],
) -> None:
    target_ids: dict[tuple[str, str], str] = {}
    for canonical_id, name in customer_names.items():
        target_ids[(canonical_id, "organization")] = name
    for canonical_id, name in contact_names.items():
        target_ids[(canonical_id, "contact")] = name
    for case_id, doc in sales_documents.items():
        target_ids[(f"operion:e2:sales_order:{case_id}", "sales_order")] = doc["name"]
        target_ids[
            (
                f"operion:e2:sales_order_line:{case_id}",
                "sales_order_line",
            )
        ] = doc["items"][0]["name"]
    for case_id, doc in purchase_documents.items():
        target_ids[(f"operion:e2:purchase_order:{case_id}", "purchase_order")] = doc[
            "name"
        ]
        target_ids[
            (
                f"operion:e2:purchase_order_line:{case_id}",
                "purchase_order_line",
            )
        ] = doc["items"][0]["name"]
    for row in identity_rows:
        if row["target_system"] != "erpnext":
            continue
        target_id = target_ids.get((row["canonical_id"], row["entity_type"]))
        if target_id:
            row["target_id"] = target_id
            row["load_status"] = "loaded"
            row["error"] = ""


def _upsert_erpnext(
    client: ERPNextAdminClient,
    identity_rows: list[dict[str, str]],
) -> dict[str, Any]:
    customer_names, contact_names, warehouse, settings_before = _seed_erpnext_masters(
        client
    )
    stock_entry = _seed_opening_stock(client, warehouse)
    sales = _seed_sales_orders(
        client, customer_names[E2_CUSTOMERS[0]["canonical_id"]], warehouse
    )
    purchases = _seed_purchase_orders(client, warehouse)
    delivery = _seed_partial_delivery(client, sales["F05"])
    _update_erpnext_identities(
        identity_rows, customer_names, contact_names, sales, purchases
    )
    bins = client.list(
        "Bin",
        [
            "name",
            "item_code",
            "warehouse",
            "actual_qty",
            "reserved_qty",
            "reserved_stock",
            "ordered_qty",
            "projected_qty",
        ],
        [["warehouse", "=", warehouse]],
    )
    reservations = client.list(
        "Stock Reservation Entry",
        [
            "name",
            "voucher_no",
            "item_code",
            "warehouse",
            "reserved_qty",
            "status",
        ],
        [["voucher_no", "=", sales["F04-reservation"]["name"]]],
    )
    return {
        "customers": customer_names,
        "contacts": contact_names,
        "warehouse": warehouse,
        "stock_settings_before": settings_before,
        "stock_settings_after": {
            "enable_stock_reservation": 1,
            "allow_partial_reservation": 1,
            "allow_negative_stock": 0,
        },
        "stock_entry": stock_entry["name"],
        "sales_orders": {key: value["name"] for key, value in sales.items()},
        "purchase_orders": {key: value["name"] for key, value in purchases.items()},
        "delivery_note": delivery["name"],
        "bins": bins,
        "stock_reservations": reservations,
    }


def _upsert_twenty(
    client: TwentyClient, identity_rows: list[dict[str, str]]
) -> dict[str, Any]:
    companies = client.companies()
    company_by_key = {
        row.get("wwiExternalId", ""): row
        for row in companies
        if row.get("wwiExternalId")
    }
    people = client.people()
    person_by_key = {
        row.get("wwiExternalId", ""): row for row in people if row.get("wwiExternalId")
    }
    result = {"companies": {}, "people": {}}
    for spec in E2_CUSTOMERS:
        payload = {
            "name": E2_CUSTOMER_NAME,
            "wwiExternalId": spec["canonical_id"],
        }
        current = company_by_key.get(spec["canonical_id"])
        company = (
            client.update_company(current["id"], payload)
            if current
            else client.create_company(payload)
        )
        result["companies"][spec["canonical_id"]] = company["id"]
        person_payload = {
            "name": {
                "firstName": spec["contact_first_name"],
                "lastName": spec["contact_last_name"],
            },
            "companyId": company["id"],
            "wwiExternalId": spec["contact_id"],
        }
        current_person = person_by_key.get(spec["contact_id"])
        person = (
            client.update_person(current_person["id"], person_payload)
            if current_person
            else client.create_person(person_payload)
        )
        result["people"][spec["contact_id"]] = person["id"]

    target_ids = {**result["companies"], **result["people"]}
    for row in identity_rows:
        if row["target_system"] == "twenty" and row["canonical_id"] in target_ids:
            row["target_id"] = target_ids[row["canonical_id"]]
            row["load_status"] = "loaded"
            row["error"] = ""
    return result


def seed_e2_targets(
    identity_map: Path,
    report_path: Path,
    env_file: Path = Path(".env"),
) -> dict[str, Any]:
    values = read_env(env_file)
    _, identity_rows = _read_csv(identity_map)
    twenty = TwentyClient(
        values.get("TWENTY_API_BASE_URL", "http://localhost:3000"),
        values.get("TWENTY_API_KEY", ""),
    )
    twenty_result = _upsert_twenty(twenty, identity_rows)
    erpnext = ERPNextAdminClient(
        values.get("ERPNEXT_API_BASE_URL", "http://localhost:8080"),
        values.get("ERPNEXT_API_KEY", ""),
    )
    erpnext_result = _upsert_erpnext(erpnext, identity_rows)
    _write_csv(identity_map, IDENTITY_FIELDS, identity_rows)
    report = {
        "status": "passed",
        "batch_id": E2_BATCH_ID,
        "twenty": twenty_result,
        "erpnext": erpnext_result,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
