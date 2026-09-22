from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .identity_readback import IDENTITY_FIELDS
from .interview_demo import (
    FILE_FIELDS,
    _identity_rows,
    _write_csv,
    apply_interview_demo,
    provision_plan,
)
from .sqlserver import SqlServer

DATASET_VERSION = "interview-wwi-v1"
DEFAULT_BUSINESS_DATE = date(2016, 5, 31)
DEFAULT_SEED = 42
DEFAULT_SOURCE_MANIFEST = Path("data/raw/wwi/20260912T000000Z/source_manifest.json")
EXPECTED_SOURCE_SHA256 = (
    "e842bad6ce02f74f166947e559dab1b476edd7eaae3da2ab9e3f522f1dd87124"
)

# The IDs are a versioned selection contract. The seed documents how the original
# candidate set was chosen; later runs do not silently reshuffle the public sample.
CUSTOMER_ORDER_COUNTS = {
    58: 4,
    60: 0,
    65: 10,
    88: 0,
    183: 4,
    463: 3,
    840: 3,
    935: 2,
    961: 2,
    1011: 2,
}
CUSTOMER_ALTERNATE_CONTACT_IDS = (58, 60, 65, 88)
SUPPLIER_IDS = (3, 6, 7, 8, 9)
PRODUCT_IDS = (177, 178, 179, 180, 181, 182, 183, 184, 189, 193, 203, 204)
PURCHASE_ORDER_COUNT = 15
EXPECTED_COUNTS = {
    "organizations": 15,
    "contacts": 20,
    "products": 12,
    "sales_orders": 30,
    "sales_order_lines": 31,
    "purchase_orders": 15,
    "purchase_order_lines": 43,
    "fulfillment_scenarios": 0,
}


def _ids(values: Any) -> str:
    return ",".join(str(int(value)) for value in values)


def _money(value: Any) -> str:
    return str(
        Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _number(value: Any) -> str:
    normalized = format(Decimal(str(value or 0)).normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _date(value: Any) -> str:
    return str(value or "")[:10]


def _source_profile(db: SqlServer) -> dict[str, Any]:
    rows = db.query_json(
        """
SELECT
  (SELECT COUNT_BIG(*) FROM Sales.Customers) AS customers,
  (SELECT COUNT_BIG(*) FROM Purchasing.Suppliers) AS suppliers,
  (SELECT COUNT_BIG(*) FROM Warehouse.StockItems) AS products,
  (SELECT COUNT_BIG(*) FROM Sales.Orders) AS sales_orders,
  (SELECT COUNT_BIG(*) FROM Purchasing.PurchaseOrders) AS purchase_orders,
  CONVERT(varchar(10), (SELECT MAX(OrderDate) FROM Sales.Orders), 23)
    AS sales_order_max_date,
  CONVERT(varchar(10), (SELECT MAX(OrderDate) FROM Purchasing.PurchaseOrders), 23)
    AS purchase_order_max_date
"""
    )
    if len(rows) != 1:
        raise RuntimeError("WWI source profile query did not return one row")
    return rows[0]


def _assert_source_profile(profile: dict[str, Any]) -> None:
    expected = {
        "customers": 663,
        "suppliers": 13,
        "products": 227,
        "sales_orders": 73595,
        "purchase_orders": 2074,
        "sales_order_max_date": "2016-05-31",
        "purchase_order_max_date": "2016-05-31",
    }
    mismatches = {
        key: {"expected": value, "actual": profile.get(key)}
        for key, value in expected.items()
        if profile.get(key) != value
    }
    if mismatches:
        raise RuntimeError(
            "WWI database does not match the pinned v1 source profile: "
            + json.dumps(mismatches, sort_keys=True)
        )


def extract_interview_wwi(db: SqlServer) -> tuple[dict[str, list[dict]], dict]:
    profile = _source_profile(db)
    _assert_source_profile(profile)
    customer_ids = _ids(sorted(CUSTOMER_ORDER_COUNTS))
    supplier_ids = _ids(SUPPLIER_IDS)
    product_ids = _ids(PRODUCT_IDS)

    customers = db.query_json(
        f"""
SELECT c.CustomerID, c.CustomerName, c.PrimaryContactPersonID,
  c.AlternateContactPersonID, c.PhoneNumber, c.WebsiteURL,
  c.DeliveryAddressLine1, c.DeliveryAddressLine2, c.DeliveryPostalCode,
  c.PaymentDays, c.CreditLimit,
  city.CityName AS DeliveryCity, state.StateProvinceName AS DeliveryState,
  country.CountryName AS DeliveryCountry,
  CONVERT(varchar(10), c.AccountOpenedDate, 23) AS AccountOpenedDate,
  CONVERT(varchar(33), c.ValidFrom, 127) AS LastUpdate
FROM Sales.Customers c
JOIN Application.Cities city ON city.CityID = c.DeliveryCityID
JOIN Application.StateProvinces state ON state.StateProvinceID = city.StateProvinceID
JOIN Application.Countries country ON country.CountryID = state.CountryID
WHERE c.CustomerID IN ({customer_ids})
ORDER BY c.CustomerID
"""
    )
    suppliers = db.query_json(
        f"""
SELECT s.SupplierID, s.SupplierName, s.PrimaryContactPersonID,
  s.AlternateContactPersonID, s.PhoneNumber, s.WebsiteURL,
  s.DeliveryAddressLine1, s.DeliveryAddressLine2, s.DeliveryPostalCode,
  s.PaymentDays,
  city.CityName AS DeliveryCity, state.StateProvinceName AS DeliveryState,
  country.CountryName AS DeliveryCountry,
  CONVERT(varchar(33), s.ValidFrom, 127) AS CreationDate,
  CONVERT(varchar(33), s.ValidFrom, 127) AS LastUpdate
FROM Purchasing.Suppliers s
JOIN Application.Cities city ON city.CityID = s.DeliveryCityID
JOIN Application.StateProvinces state ON state.StateProvinceID = city.StateProvinceID
JOIN Application.Countries country ON country.CountryID = state.CountryID
WHERE s.SupplierID IN ({supplier_ids})
ORDER BY s.SupplierID
"""
    )
    products = db.query_json(
        f"""
SELECT si.StockItemID, si.StockItemName, si.SupplierID, si.QuantityPerOuter,
  up.PackageTypeName AS UnitPackage, op.PackageTypeName AS OuterPackage,
  si.Brand, si.Size, si.Barcode, si.TaxRate, si.UnitPrice,
  h.QuantityOnHand, h.BinLocation
FROM Warehouse.StockItems si
JOIN Warehouse.PackageTypes up ON up.PackageTypeID = si.UnitPackageID
JOIN Warehouse.PackageTypes op ON op.PackageTypeID = si.OuterPackageID
LEFT JOIN Warehouse.StockItemHoldings h ON h.StockItemID = si.StockItemID
WHERE si.StockItemID IN ({product_ids})
ORDER BY si.StockItemID
"""
    )

    active_customers = _ids(
        customer_id for customer_id, count in CUSTOMER_ORDER_COUNTS.items() if count
    )
    rank_clauses = " OR ".join(
        f"(CustomerID = {customer_id} AND selection_rank <= {count})"
        for customer_id, count in CUSTOMER_ORDER_COUNTS.items()
        if count
    )
    sales_orders = db.query_json(
        f"""
WITH eligible AS (
  SELECT o.OrderID, o.CustomerID, o.SalespersonPersonID, o.ContactPersonID,
    o.OrderDate, o.ExpectedDeliveryDate, o.CustomerPurchaseOrderNumber,
    o.IsUndersupplyBackordered, o.PickingCompletedWhen,
    ROW_NUMBER() OVER (
      PARTITION BY o.CustomerID ORDER BY o.OrderID DESC
    ) AS selection_rank
  FROM Sales.Orders o
  WHERE o.CustomerID IN ({active_customers})
    AND o.OrderID IN (
      SELECT ol.OrderID
      FROM Sales.OrderLines ol
      GROUP BY ol.OrderID
      HAVING COUNT(*) BETWEEN 1 AND 4
        AND SUM(
          CASE WHEN ol.StockItemID IN ({product_ids}) THEN 0 ELSE 1 END
        ) = 0
    )
)
SELECT OrderID, CustomerID, SalespersonPersonID, ContactPersonID,
  CONVERT(varchar(10), OrderDate, 23) AS OrderDate,
  CONVERT(varchar(10), ExpectedDeliveryDate, 23) AS ExpectedDeliveryDate,
  CustomerPurchaseOrderNumber, IsUndersupplyBackordered,
  CONVERT(varchar(33), PickingCompletedWhen, 127) AS PickingCompletedWhen
FROM eligible
WHERE {rank_clauses}
ORDER BY CustomerID, selection_rank
"""
    )
    sales_order_ids = _ids(row["OrderID"] for row in sales_orders)
    sales_lines = db.query_json(
        f"""
SELECT ol.OrderLineID, ol.OrderID, ol.StockItemID, ol.Description,
  ol.Quantity, ol.UnitPrice, ol.TaxRate, ol.PickedQuantity,
  CONVERT(varchar(33), ol.PickingCompletedWhen, 127) AS PickingCompletedWhen
FROM Sales.OrderLines ol
WHERE ol.OrderID IN ({sales_order_ids})
ORDER BY ol.OrderID, ol.OrderLineID
"""
    )

    purchase_orders = db.query_json(
        f"""
WITH eligible AS (
  SELECT po.PurchaseOrderID
  FROM Purchasing.PurchaseOrders po
  JOIN Purchasing.PurchaseOrderLines pol
    ON pol.PurchaseOrderID = po.PurchaseOrderID
  GROUP BY po.PurchaseOrderID
  HAVING COUNT(*) BETWEEN 1 AND 4
    AND SUM(
      CASE WHEN pol.StockItemID IN ({product_ids}) THEN 0 ELSE 1 END
    ) = 0
), selected AS (
  SELECT TOP ({PURCHASE_ORDER_COUNT}) PurchaseOrderID
  FROM eligible
  ORDER BY PurchaseOrderID DESC
)
SELECT po.PurchaseOrderID, po.SupplierID, po.ContactPersonID,
  CONVERT(varchar(10), po.OrderDate, 23) AS OrderDate,
  CONVERT(varchar(10), po.ExpectedDeliveryDate, 23) AS ExpectedDeliveryDate,
  po.SupplierReference, po.IsOrderFinalized
FROM Purchasing.PurchaseOrders po
JOIN selected s ON s.PurchaseOrderID = po.PurchaseOrderID
ORDER BY po.PurchaseOrderID
"""
    )
    purchase_order_ids = _ids(row["PurchaseOrderID"] for row in purchase_orders)
    purchase_lines = db.query_json(
        f"""
SELECT pol.PurchaseOrderLineID, pol.PurchaseOrderID, pol.StockItemID,
  pol.OrderedOuters, pol.Description, pol.ReceivedOuters,
  pol.ExpectedUnitPricePerOuter,
  CONVERT(varchar(10), pol.LastReceiptDate, 23) AS LastReceiptDate,
  pol.IsOrderLineFinalized
FROM Purchasing.PurchaseOrderLines pol
WHERE pol.PurchaseOrderID IN ({purchase_order_ids})
ORDER BY pol.PurchaseOrderID, pol.PurchaseOrderLineID
"""
    )

    selected_people: set[int] = set()
    alternate_customer_ids = set(CUSTOMER_ALTERNATE_CONTACT_IDS)
    for row in customers:
        selected_people.add(int(row["PrimaryContactPersonID"]))
        if int(row["CustomerID"]) in alternate_customer_ids:
            selected_people.add(int(row["AlternateContactPersonID"]))
    for row in suppliers:
        selected_people.add(int(row["PrimaryContactPersonID"]))
    selected_people.update(int(row["ContactPersonID"]) for row in purchase_orders)
    people = db.query_json(
        f"""
SELECT p.PersonID, p.FullName, p.PreferredName, p.IsEmployee,
  p.IsSalesperson, p.PhoneNumber, p.EmailAddress
FROM Application.People p
WHERE p.PersonID IN ({_ids(sorted(selected_people))})
ORDER BY p.PersonID
"""
    )
    return (
        {
            "customers": customers,
            "suppliers": suppliers,
            "products": products,
            "people": people,
            "sales_orders": sales_orders,
            "sales_lines": sales_lines,
            "purchase_orders": purchase_orders,
            "purchase_lines": purchase_lines,
        },
        profile,
    )


def build_interview_wwi(
    source: dict[str, list[dict]],
    *,
    business_date: date = DEFAULT_BUSINESS_DATE,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[dict[str, Any]]]:
    common = {
        "data_class": "public_sample",
        "dataset_version": DATASET_VERSION,
        "business_date": business_date.isoformat(),
        "seed": str(seed),
    }
    product_by_id = {int(row["StockItemID"]): row for row in source["products"]}
    organizations: list[dict[str, Any]] = []
    for role, rows, id_key, name_key in (
        ("customer", source["customers"], "CustomerID", "CustomerName"),
        ("supplier", source["suppliers"], "SupplierID", "SupplierName"),
    ):
        for row in rows:
            source_id = int(row[id_key])
            organizations.append(
                {
                    "canonical_id": f"wwi:organization:{role}:{source_id}",
                    "source_system": "wwi",
                    "source_id": str(source_id),
                    "name": row[name_key],
                    "roles": role,
                    "primary_contact_source_id": str(
                        row.get("PrimaryContactPersonID") or ""
                    ),
                    "phone": row.get("PhoneNumber") or "",
                    "website": row.get("WebsiteURL") or "",
                    "address_line_1": row.get("DeliveryAddressLine1") or "",
                    "address_line_2": row.get("DeliveryAddressLine2") or "",
                    "city": row.get("DeliveryCity") or "",
                    "state": row.get("DeliveryState") or "",
                    "country": row.get("DeliveryCountry") or "",
                    "postal_code": row.get("DeliveryPostalCode") or "",
                    "payment_days": _number(row.get("PaymentDays")),
                    "credit_limit": (
                        _money(row.get("CreditLimit")) if role == "customer" else ""
                    ),
                    "created_at": row.get("AccountOpenedDate")
                    or row.get("CreationDate")
                    or "",
                    "updated_at": row.get("LastUpdate") or "",
                    **common,
                }
            )

    person_organization: dict[int, tuple[str, str]] = {}
    alternate_customer_ids = set(CUSTOMER_ALTERNATE_CONTACT_IDS)
    for row in source["customers"]:
        customer_id = int(row["CustomerID"])
        organization_id = f"wwi:organization:customer:{customer_id}"
        person_organization[int(row["PrimaryContactPersonID"])] = (
            organization_id,
            "customer primary contact",
        )
        if customer_id in alternate_customer_ids:
            person_organization[int(row["AlternateContactPersonID"])] = (
                organization_id,
                "customer alternate contact",
            )
    for row in source["suppliers"]:
        supplier_id = int(row["SupplierID"])
        person_organization[int(row["PrimaryContactPersonID"])] = (
            f"wwi:organization:supplier:{supplier_id}",
            "supplier primary contact",
        )
    for row in source["purchase_orders"]:
        person_organization.setdefault(
            int(row["ContactPersonID"]),
            ("", "internal purchasing contact"),
        )
    contacts = []
    for row in source["people"]:
        person_id = int(row["PersonID"])
        organization_id, relationship = person_organization[person_id]
        contacts.append(
            {
                "canonical_id": f"wwi:contact:{person_id}",
                "source_system": "wwi",
                "source_id": str(person_id),
                "full_name": row["FullName"],
                "preferred_name": row.get("PreferredName") or "",
                "email": row.get("EmailAddress") or "",
                "phone": row.get("PhoneNumber") or "",
                "company_canonical_id": organization_id,
                "is_employee": str(bool(row.get("IsEmployee"))).lower(),
                "is_salesperson": str(bool(row.get("IsSalesperson"))).lower(),
                "relationship": relationship,
                **common,
            }
        )

    products = [
        {
            "canonical_id": f"wwi:product:{row['StockItemID']}",
            "source_system": "wwi",
            "source_id": str(row["StockItemID"]),
            "name": row["StockItemName"],
            "supplier_source_id": str(row["SupplierID"]),
            "uom": row["UnitPackage"],
            "outer_uom": row["OuterPackage"],
            "units_per_outer": _number(row["QuantityPerOuter"]),
            "brand": row.get("Brand") or "",
            "size": row.get("Size") or "",
            "barcode": row.get("Barcode") or "",
            "unit_price_ex_tax": _money(row["UnitPrice"]),
            "tax_rate_percent": _number(row["TaxRate"]),
            "quantity_on_hand": _number(row.get("QuantityOnHand")),
            "warehouse": "WWI Main Warehouse",
            "bin_location": row.get("BinLocation") or "",
            "currency": "USD",
            **common,
        }
        for row in source["products"]
    ]

    sales_lines: list[dict[str, Any]] = []
    sales_totals: defaultdict[int, Decimal] = defaultdict(Decimal)
    for row in source["sales_lines"]:
        order_id = int(row["OrderID"])
        quantity = Decimal(str(row["Quantity"]))
        picked = Decimal(str(row.get("PickedQuantity") or 0))
        unit_price = Decimal(str(row["UnitPrice"]))
        amount = quantity * unit_price
        sales_totals[order_id] += amount
        product = product_by_id[int(row["StockItemID"])]
        sales_lines.append(
            {
                "canonical_id": f"wwi:sales_order_line:{row['OrderLineID']}",
                "source_system": "wwi",
                "source_id": str(row["OrderLineID"]),
                "sales_order_canonical_id": f"wwi:sales_order:{order_id}",
                "product_canonical_id": f"wwi:product:{row['StockItemID']}",
                "description": row["Description"],
                "uom": product["UnitPackage"],
                "ordered_quantity": _number(quantity),
                "picked_quantity": _number(picked),
                "unpicked_quantity": _number(max(quantity - picked, Decimal(0))),
                "delivered_quantity": "",
                "delivery_evidence": "unknown_not_provided_by_wwi_order_lines",
                "open_quantity": "",
                "unit_price_ex_tax": _money(unit_price),
                "tax_rate_percent": _number(row["TaxRate"]),
                "net_amount": _money(amount),
                "currency": "USD",
                **common,
            }
        )
    sales_orders = []
    for row in source["sales_orders"]:
        order_id = int(row["OrderID"])
        status = "picked" if row.get("PickingCompletedWhen") else "open"
        sales_orders.append(
            {
                "canonical_id": f"wwi:sales_order:{order_id}",
                "source_system": "wwi",
                "source_id": str(order_id),
                "customer_canonical_id": (
                    f"wwi:organization:customer:{row['CustomerID']}"
                ),
                "contact_canonical_id": f"wwi:contact:{row['ContactPersonID']}",
                "salesperson_canonical_id": "",
                "order_date": _date(row["OrderDate"]),
                "expected_delivery_date": _date(row["ExpectedDeliveryDate"]),
                "customer_po_number": row.get("CustomerPurchaseOrderNumber") or "",
                "source_status": status,
                "docstatus": "",
                "business_status": status,
                "currency": "USD",
                "net_total_ex_tax": _money(sales_totals[order_id]),
                **common,
            }
        )

    purchase_lines: list[dict[str, Any]] = []
    purchase_totals: defaultdict[int, Decimal] = defaultdict(Decimal)
    for row in source["purchase_lines"]:
        order_id = int(row["PurchaseOrderID"])
        product = product_by_id[int(row["StockItemID"])]
        factor = Decimal(str(product["QuantityPerOuter"]))
        ordered = Decimal(str(row["OrderedOuters"]))
        received = Decimal(str(row["ReceivedOuters"]))
        outer_price = Decimal(str(row["ExpectedUnitPricePerOuter"]))
        amount = ordered * outer_price
        purchase_totals[order_id] += amount
        purchase_lines.append(
            {
                "canonical_id": f"wwi:purchase_order_line:{row['PurchaseOrderLineID']}",
                "source_system": "wwi",
                "source_id": str(row["PurchaseOrderLineID"]),
                "purchase_order_canonical_id": f"wwi:purchase_order:{order_id}",
                "product_canonical_id": f"wwi:product:{row['StockItemID']}",
                "description": row["Description"],
                "source_uom": product["OuterPackage"],
                "canonical_uom": product["UnitPackage"],
                "units_per_outer": _number(factor),
                "ordered_outers": _number(ordered),
                "received_outers": _number(received),
                "open_quantity": _number(max(ordered - received, Decimal(0)) * factor),
                "expected_unit_price_per_outer": _money(outer_price),
                "expected_unit_price_each": format(
                    (outer_price / factor).quantize(Decimal("0.000001")), "f"
                ),
                "net_amount": _money(amount),
                "currency": "USD",
                "last_receipt_date": _date(row.get("LastReceiptDate")),
                **common,
            }
        )
    purchase_orders = []
    for row in source["purchase_orders"]:
        order_id = int(row["PurchaseOrderID"])
        status = "finalized" if row.get("IsOrderFinalized") else "open"
        purchase_orders.append(
            {
                "canonical_id": f"wwi:purchase_order:{order_id}",
                "source_system": "wwi",
                "source_id": str(order_id),
                "supplier_canonical_id": (
                    f"wwi:organization:supplier:{row['SupplierID']}"
                ),
                "contact_canonical_id": f"wwi:contact:{row['ContactPersonID']}",
                "order_date": _date(row["OrderDate"]),
                "expected_delivery_date": _date(row["ExpectedDeliveryDate"]),
                "supplier_reference": row.get("SupplierReference") or "",
                "source_status": status,
                "docstatus": "",
                "business_status": status,
                "currency": "USD",
                "net_total_ex_tax": _money(purchase_totals[order_id]),
                **common,
            }
        )
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


def prepare_interview_wwi(
    output_directory: Path,
    identity_map: Path,
    *,
    source_manifest: Path = DEFAULT_SOURCE_MANIFEST,
    container: str = "enterprise-demo-mssql",
    business_date: date = DEFAULT_BUSINESS_DATE,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    if business_date != DEFAULT_BUSINESS_DATE or seed != DEFAULT_SEED:
        raise ValueError(
            "interview-wwi-v1 pins business_date=2016-05-31 and seed=42; "
            "use a new dataset version for a different selection contract"
        )
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    if manifest.get("sha256") != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("WWI source manifest SHA-256 does not match the pinned v1")
    if manifest.get("data_version") != "wide-world-importers-v1.0":
        raise RuntimeError("WWI source manifest data version is not v1.0")
    source, profile = extract_interview_wwi(SqlServer(container=container))
    data = build_interview_wwi(source, business_date=business_date, seed=seed)
    for filename, rows in data.items():
        _write_csv(output_directory / f"{filename}.csv", rows)
    identity_rows = _identity_rows(
        data, source_system="wwi", dataset_version=DATASET_VERSION
    )
    identity_map.parent.mkdir(parents=True, exist_ok=True)
    with identity_map.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=IDENTITY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(identity_rows)
    dataset_manifest = {
        "dataset_version": DATASET_VERSION,
        "mapping_revision": "interview-wwi-v1.1",
        "source_system": "wwi",
        "data_class": "public_sample",
        "seed": seed,
        "business_date": business_date.isoformat(),
        "source_observed_at": manifest["acquired_at_utc"],
        "source_snapshot": {
            "data_version": manifest["data_version"],
            "sha256": manifest["sha256"],
            "usage_class": manifest["usage_class"],
        },
        "source_profile": profile,
        "selection": {
            "customer_order_counts": {
                str(key): value for key, value in CUSTOMER_ORDER_COUNTS.items()
            },
            "supplier_ids": list(SUPPLIER_IDS),
            "product_ids": list(PRODUCT_IDS),
            "purchase_order_rule": (
                "latest 15 complete 1-4-line orders using only selected products"
            ),
        },
        "currency": "USD",
        "currency_basis": (
            "dataset-level assumption for the US-oriented WWI v1 sample; "
            "WWI order rows do not store a currency code"
        ),
        "amount_basis": "tax_exclusive",
        "mapping_changes": [
            "PickedQuantity is mapped to picked_quantity, never delivered_quantity",
            "delivered_quantity is blank without delivery evidence",
            "purchase imports convert outer quantities to base-unit quantities",
        ],
        "counts": {name: len(rows) for name, rows in data.items()},
        "identity_rows": len(identity_rows),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "dataset.json").write_text(
        json.dumps(dataset_manifest, indent=2) + "\n", encoding="utf-8"
    )
    return dataset_manifest


def validate_interview_wwi(directory: Path) -> dict[str, Any]:
    data: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    for filename, expected_fields in FILE_FIELDS.items():
        path = directory / f"{filename}.csv"
        try:
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != expected_fields:
                    errors.append(f"{filename}: header does not match canonical spec")
                data[filename] = list(reader)
        except OSError:
            errors.append(f"missing file: {path.name}")
            data[filename] = []
    for name, expected in EXPECTED_COUNTS.items():
        if len(data[name]) != expected:
            errors.append(f"{name}: expected {expected}, got {len(data[name])}")

    ids = {
        name: {row["canonical_id"] for row in rows}
        for name, rows in data.items()
        if name != "fulfillment_scenarios"
    }
    for name, rows in data.items():
        for row in rows:
            if row.get("source_system") not in (None, "wwi"):
                errors.append(f"{name}: non-WWI source record")
            if row.get("data_class") not in (None, "public_sample"):
                errors.append(f"{name}: record is not public_sample")
            if row.get("dataset_version") not in (None, DATASET_VERSION):
                errors.append(f"{name}: wrong dataset_version")
    for row in data["contacts"]:
        if (
            row["company_canonical_id"]
            and row["company_canonical_id"] not in ids["organizations"]
        ):
            errors.append(f"contact has missing organization: {row['canonical_id']}")
    for row in data["sales_orders"]:
        if row["customer_canonical_id"] not in ids["organizations"]:
            errors.append(f"sales order has missing customer: {row['canonical_id']}")
        if row["contact_canonical_id"] not in ids["contacts"]:
            errors.append(f"sales order has missing contact: {row['canonical_id']}")
    for row in data["purchase_orders"]:
        if row["supplier_canonical_id"] not in ids["organizations"]:
            errors.append(f"purchase order has missing supplier: {row['canonical_id']}")
        if row["contact_canonical_id"] not in ids["contacts"]:
            errors.append(f"purchase order has missing contact: {row['canonical_id']}")

    line_specs = (
        ("sales_orders", "sales_order_lines", "sales_order_canonical_id"),
        ("purchase_orders", "purchase_order_lines", "purchase_order_canonical_id"),
    )
    for order_table, line_table, relation in line_specs:
        by_order: defaultdict[str, Decimal] = defaultdict(Decimal)
        line_counts: Counter[str] = Counter()
        for row in data[line_table]:
            if row[relation] not in ids[order_table]:
                errors.append(f"line has missing order: {row['canonical_id']}")
            if row["product_canonical_id"] not in ids["products"]:
                errors.append(f"line has missing product: {row['canonical_id']}")
            by_order[row[relation]] += Decimal(row["net_amount"])
            line_counts[row[relation]] += 1
            if line_table == "purchase_order_lines":
                source_amount = (
                    Decimal(row["ordered_outers"])
                    * Decimal(row["expected_unit_price_per_outer"])
                ).quantize(Decimal("0.01"))
                if source_amount != Decimal(row["net_amount"]):
                    errors.append(
                        f"purchase source amount mismatch: {row['canonical_id']}"
                    )
        for row in data[order_table]:
            canonical_id = row["canonical_id"]
            if line_counts[canonical_id] not in range(1, 5):
                errors.append(f"order does not have 1-4 lines: {canonical_id}")
            if by_order[canonical_id] != Decimal(row["net_total_ex_tax"]):
                errors.append(f"amount mismatch: {canonical_id}")

    sales_by_customer = Counter(
        row["customer_canonical_id"] for row in data["sales_orders"]
    )
    customer_ids = [
        row["canonical_id"]
        for row in data["organizations"]
        if row["roles"] == "customer"
    ]
    if not any(sales_by_customer[customer_id] == 0 for customer_id in customer_ids):
        errors.append("no zero-sales-order customer")
    if max(sales_by_customer.values(), default=0) < 8:
        errors.append("no customer has at least eight sales orders")
    purchases_by_supplier = Counter(
        row["supplier_canonical_id"] for row in data["purchase_orders"]
    )
    supplier_ids = [
        row["canonical_id"]
        for row in data["organizations"]
        if row["roles"] == "supplier"
    ]
    if not any(purchases_by_supplier[supplier_id] == 0 for supplier_id in supplier_ids):
        errors.append("no zero-purchase-order supplier")
    if {int(row["source_id"]) for row in data["products"]} != set(PRODUCT_IDS):
        errors.append("product selection differs from interview-wwi-v1 contract")

    for row in data["sales_order_lines"]:
        ordered = Decimal(row["ordered_quantity"])
        picked = Decimal(row["picked_quantity"])
        unpicked = Decimal(row["unpicked_quantity"])
        if picked + unpicked != ordered:
            errors.append(f"picked/unpicked mismatch: {row['canonical_id']}")
        if row["delivered_quantity"]:
            errors.append(f"delivery quantity must be unknown: {row['canonical_id']}")
        if row["delivery_evidence"] != "unknown_not_provided_by_wwi_order_lines":
            errors.append(f"delivery evidence marker mismatch: {row['canonical_id']}")
        if row["open_quantity"]:
            errors.append(
                f"delivery-open quantity must be unknown: {row['canonical_id']}"
            )

    # Independent gold facts copied from the pinned WWI source, not recomputed by
    # the transformation under test.
    sales_gold = next(
        (row for row in data["sales_order_lines"] if row["source_id"] == "210128"),
        None,
    )
    if sales_gold is None or (
        sales_gold["ordered_quantity"],
        sales_gold["picked_quantity"],
        sales_gold["unpicked_quantity"],
        sales_gold["delivered_quantity"],
    ) != ("48", "48", "0", ""):
        errors.append("gold sales line 210128 quantity semantics changed")
    purchase_gold = next(
        (row for row in data["purchase_order_lines"] if row["source_id"] == "8240"),
        None,
    )
    if purchase_gold is None or (
        purchase_gold["ordered_outers"],
        purchase_gold["units_per_outer"],
        purchase_gold["expected_unit_price_each"],
        purchase_gold["net_amount"],
    ) != ("1592", "25", "1.900000", "75620.00"):
        errors.append("gold purchase line 8240 amount semantics changed")

    return {
        "status": "passed" if not errors else "failed",
        "dataset_version": DATASET_VERSION,
        "counts": {name: len(rows) for name, rows in data.items()},
        "errors": errors,
    }


def provision_wwi_plan(
    directory: Path, *, selection_plan: Path | None = None
) -> dict[str, Any]:
    return provision_plan(
        directory,
        validator=validate_interview_wwi,
        dataset_version=DATASET_VERSION,
        selection_plan=selection_plan,
    )


def apply_interview_wwi(
    directory: Path,
    identity_map: Path,
    admin_env: Path,
    *,
    selection_plan: Path | None = None,
) -> dict[str, Any]:
    return apply_interview_demo(
        directory,
        identity_map,
        admin_env,
        validator=validate_interview_wwi,
        dataset_version=DATASET_VERSION,
        selection_plan=selection_plan,
    )
