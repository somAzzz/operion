from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlsplit

from .download import sha256_file
from .sqlserver import SqlServer

MAPPING_VERSION = "wwi-minimal-v1"
SCENARIO_VERSION = "fulfillment-v1"
TWENTY_COMPANY_HEADERS = [
    "Account Owner (ID)",
    "Address / Address 1",
    "Address / Address 2",
    "Address / City",
    "Address / State",
    "Address / Country",
    "Address / Post Code",
    "Annual Revenue / Amount",
    "Annual Revenue / Currency",
    "Creation date",
    "Domain Name / Link URL",
    "Domain Name / Link Label",
    "Domain Name / Secondary Links",
    "Id",
    "Linkedin / Link URL",
    "Linkedin / Link Label",
    "Linkedin / Secondary Links",
    "Name",
    "WWI External ID",
    "Last update",
]
TWENTY_PEOPLE_HEADERS = [
    "First Name",
    "Last Name",
    "Primary Email",
    "Primary Phone",
    "Company WWI External ID",
    "WWI External ID",
]
ERPNEXT_COMPANY = "AI Demo GmbH"
ERPNEXT_CURRENCY = "EUR"
ERPNEXT_TERRITORY = "Rest Of The World"
ERPNEXT_UOM_MAP = {"Each": "Unit"}
ERPNEXT_CUSTOMER_HEADERS = [
    "ID",
    "Customer Name",
    "Customer Type",
    "Customer Group",
    "Territory",
    "Operion Source Key",
]
ERPNEXT_SUPPLIER_HEADERS = [
    "ID",
    "Supplier Name",
    "Supplier Type",
    "Supplier Group",
    "Operion Source Key",
]
ERPNEXT_ITEM_HEADERS = [
    "ID",
    "Item Code",
    "Item Name",
    "Item Group",
    "Default Unit of Measure",
    "Maintain Stock",
    "Standard Selling Rate",
    "Operion Source Key",
]
ERPNEXT_CONTACT_HEADERS = [
    "ID",
    "First Name",
    "Last Name",
    "Operion Source Key",
    "Email ID (Email IDs)",
    "Is Primary (Email IDs)",
    "Number (Contact Numbers)",
    "Is Primary Phone (Contact Numbers)",
    "Link Document Type (Links)",
    "Link Name (Links)",
]
ERPNEXT_SALES_ORDER_HEADERS = [
    "ID",
    "Series",
    "Customer",
    "Order Type",
    "Date",
    "Delivery Date",
    "Company",
    "Currency",
    "Exchange Rate",
    "Price List",
    "Price List Currency",
    "Price List Exchange Rate",
    "Customer's Purchase Order",
    "Operion Source Key",
    "WWI Source Status",
    "Item Code (Items)",
    "Item Name (Items)",
    "Delivery Date (Items)",
    "Quantity (Items)",
    "Stock UOM (Items)",
    "UOM (Items)",
    "UOM Conversion Factor (Items)",
    "Rate (Items)",
    "Amount (Items)",
    "Basic Rate (Company Currency) (Items)",
    "Amount (Company Currency) (Items)",
    "Operion Source Key (Items)",
]
ERPNEXT_PURCHASE_ORDER_HEADERS = [
    "ID",
    "Series",
    "Supplier",
    "Date",
    "Required By",
    "Company",
    "Currency",
    "Exchange Rate",
    "Price List",
    "Price List Currency",
    "Price List Exchange Rate",
    "Operion Source Key",
    "WWI Supplier Reference",
    "WWI Source Status",
    "Item Code (Items)",
    "Item Name (Items)",
    "Required By (Items)",
    "Quantity (Items)",
    "Stock UOM (Items)",
    "UOM (Items)",
    "UOM Conversion Factor (Items)",
    "Rate (Items)",
    "Amount (Items)",
    "Rate (Company Currency) (Items)",
    "Amount (Company Currency) (Items)",
    "Operion Source Key (Items)",
]


def _ids(rows: Iterable[dict], key: str) -> str:
    values = sorted({int(row[key]) for row in rows if row.get(key) is not None})
    return ",".join(str(value) for value in values) or "NULL"


def _money(value: object) -> str:
    return str(
        Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _number(value: object) -> str:
    normalized = format(Decimal(str(value or 0)).normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _date(value: object) -> str:
    return str(value or "")[:10]


def _write_csv(
    path: Path,
    rows: list[dict],
    fieldnames: list[str] | None = None,
    lineterminator: str = "\r\n",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator=lineterminator,
        )
        writer.writeheader()
        writer.writerows(rows)


def _extract(db: SqlServer, order_limit: int) -> dict[str, list[dict]]:
    orders = db.query_json(f"""
SELECT TOP ({int(order_limit)})
  o.OrderID, o.CustomerID, o.SalespersonPersonID, o.ContactPersonID,
  CONVERT(varchar(10), o.OrderDate, 23) AS OrderDate,
  CONVERT(varchar(10), o.ExpectedDeliveryDate, 23) AS ExpectedDeliveryDate,
  o.CustomerPurchaseOrderNumber, o.IsUndersupplyBackordered,
  CONVERT(varchar(33), o.PickingCompletedWhen, 127) AS PickingCompletedWhen
FROM Sales.Orders o
WHERE EXISTS (SELECT 1 FROM Sales.OrderLines ol WHERE ol.OrderID = o.OrderID)
ORDER BY o.OrderID DESC
""")
    if not orders:
        raise RuntimeError("No source orders were found")
    order_ids = _ids(orders, "OrderID")
    sales_lines = db.query_json(f"""
SELECT ol.OrderLineID, ol.OrderID, ol.StockItemID, ol.Description,
  ol.Quantity, ol.UnitPrice, ol.TaxRate, ol.PickedQuantity,
  CONVERT(varchar(33), ol.PickingCompletedWhen, 127) AS PickingCompletedWhen
FROM Sales.OrderLines ol WHERE ol.OrderID IN ({order_ids})
ORDER BY ol.OrderID, ol.OrderLineID
""")
    customer_ids = _ids(orders, "CustomerID")
    customers = db.query_json(f"""
SELECT c.CustomerID, c.CustomerName, c.PrimaryContactPersonID, c.AlternateContactPersonID,
  c.PhoneNumber, c.FaxNumber, c.WebsiteURL, c.DeliveryAddressLine1,
  c.DeliveryAddressLine2, c.DeliveryPostalCode, c.PostalAddressLine1,
  c.PostalAddressLine2, c.PostalPostalCode, c.PaymentDays, c.CreditLimit,
  city.CityName AS DeliveryCity, state.StateProvinceName AS DeliveryState,
  country.CountryName AS DeliveryCountry,
  CONVERT(varchar(10), c.AccountOpenedDate, 23) AS AccountOpenedDate,
  CONVERT(varchar(33), c.ValidFrom, 127) AS LastUpdate
FROM Sales.Customers c
JOIN Application.Cities city ON city.CityID = c.DeliveryCityID
JOIN Application.StateProvinces state ON state.StateProvinceID = city.StateProvinceID
JOIN Application.Countries country ON country.CountryID = state.CountryID
WHERE c.CustomerID IN ({customer_ids}) ORDER BY c.CustomerID
""")
    sales_item_ids = _ids(sales_lines, "StockItemID")
    purchase_orders = db.query_json(f"""
SELECT po.PurchaseOrderID, po.SupplierID, po.ContactPersonID,
  CONVERT(varchar(10), po.OrderDate, 23) AS OrderDate,
  CONVERT(varchar(10), po.ExpectedDeliveryDate, 23) AS ExpectedDeliveryDate,
  po.SupplierReference, po.IsOrderFinalized
FROM Purchasing.PurchaseOrders po
WHERE po.PurchaseOrderID IN (
  SELECT TOP ({max(order_limit, 6)}) pol.PurchaseOrderID
  FROM Purchasing.PurchaseOrderLines pol
  WHERE pol.StockItemID IN ({sales_item_ids})
  GROUP BY pol.PurchaseOrderID
  ORDER BY pol.PurchaseOrderID DESC
)
ORDER BY po.PurchaseOrderID
""")
    po_ids = _ids(purchase_orders, "PurchaseOrderID")
    purchase_lines = (
        db.query_json(f"""
SELECT pol.PurchaseOrderLineID, pol.PurchaseOrderID, pol.StockItemID,
  pol.OrderedOuters, pol.Description, pol.ReceivedOuters, pol.ExpectedUnitPricePerOuter,
  CONVERT(varchar(10), pol.LastReceiptDate, 23) AS LastReceiptDate,
  pol.IsOrderLineFinalized
FROM Purchasing.PurchaseOrderLines pol WHERE pol.PurchaseOrderID IN ({po_ids})
ORDER BY pol.PurchaseOrderID, pol.PurchaseOrderLineID
""")
        if purchase_orders
        else []
    )
    all_item_ids = sorted(
        {
            int(row["StockItemID"])
            for row in sales_lines + purchase_lines
            if row.get("StockItemID") is not None
        }
    )
    item_ids = ",".join(map(str, all_item_ids))
    products = db.query_json(f"""
SELECT si.StockItemID, si.StockItemName, si.SupplierID, si.QuantityPerOuter,
  up.PackageTypeName AS UnitPackage, op.PackageTypeName AS OuterPackage,
  si.Brand, si.Size, si.Barcode, si.TaxRate, si.UnitPrice,
  si.RecommendedRetailPrice, si.TypicalWeightPerUnit,
  h.QuantityOnHand, h.BinLocation, h.ReorderLevel, h.TargetStockLevel
FROM Warehouse.StockItems si
JOIN Warehouse.PackageTypes up ON up.PackageTypeID = si.UnitPackageID
JOIN Warehouse.PackageTypes op ON op.PackageTypeID = si.OuterPackageID
LEFT JOIN Warehouse.StockItemHoldings h ON h.StockItemID = si.StockItemID
WHERE si.StockItemID IN ({item_ids}) ORDER BY si.StockItemID
""")
    supplier_ids_set = {
        int(row["SupplierID"]) for row in purchase_orders if row.get("SupplierID")
    }
    supplier_ids_set.update(
        int(row["SupplierID"]) for row in products if row.get("SupplierID")
    )
    supplier_ids = ",".join(map(str, sorted(supplier_ids_set))) or "NULL"
    suppliers = db.query_json(f"""
SELECT s.SupplierID, s.SupplierName, s.PrimaryContactPersonID, s.AlternateContactPersonID,
  s.PhoneNumber, s.FaxNumber, s.WebsiteURL, s.DeliveryAddressLine1,
  s.DeliveryAddressLine2, s.DeliveryPostalCode, s.PostalAddressLine1,
  s.PostalAddressLine2, s.PostalPostalCode, s.PaymentDays,
  city.CityName AS DeliveryCity, state.StateProvinceName AS DeliveryState,
  country.CountryName AS DeliveryCountry,
  CONVERT(varchar(33), s.ValidFrom, 127) AS CreationDate,
  CONVERT(varchar(33), s.ValidFrom, 127) AS LastUpdate
FROM Purchasing.Suppliers s
JOIN Application.Cities city ON city.CityID = s.DeliveryCityID
JOIN Application.StateProvinces state ON state.StateProvinceID = city.StateProvinceID
JOIN Application.Countries country ON country.CountryID = state.CountryID
WHERE s.SupplierID IN ({supplier_ids}) ORDER BY s.SupplierID
""")
    person_ids_set: set[int] = set()
    for row in customers + suppliers:
        for key in ("PrimaryContactPersonID", "AlternateContactPersonID"):
            if row.get(key):
                person_ids_set.add(int(row[key]))
    for row in orders:
        for key in ("SalespersonPersonID", "ContactPersonID"):
            if row.get(key):
                person_ids_set.add(int(row[key]))
    for row in purchase_orders:
        if row.get("ContactPersonID"):
            person_ids_set.add(int(row["ContactPersonID"]))
    person_ids = ",".join(map(str, sorted(person_ids_set))) or "NULL"
    people = db.query_json(f"""
SELECT p.PersonID, p.FullName, p.PreferredName, p.IsEmployee, p.IsSalesperson,
  p.PhoneNumber, p.FaxNumber, p.EmailAddress
FROM Application.People p WHERE p.PersonID IN ({person_ids}) ORDER BY p.PersonID
""")
    return {
        "orders": orders,
        "sales_lines": sales_lines,
        "customers": customers,
        "purchase_orders": purchase_orders,
        "purchase_lines": purchase_lines,
        "products": products,
        "suppliers": suppliers,
        "people": people,
    }


def _source_profile(db: SqlServer) -> dict:
    counts = db.query_json("""
SELECT source_table, record_count FROM (
  SELECT 'Sales.Customers' AS source_table, COUNT_BIG(*) AS record_count FROM Sales.Customers
  UNION ALL SELECT 'Sales.Orders', COUNT_BIG(*) FROM Sales.Orders
  UNION ALL SELECT 'Sales.OrderLines', COUNT_BIG(*) FROM Sales.OrderLines
  UNION ALL SELECT 'Purchasing.Suppliers', COUNT_BIG(*) FROM Purchasing.Suppliers
  UNION ALL SELECT 'Purchasing.PurchaseOrders', COUNT_BIG(*) FROM Purchasing.PurchaseOrders
  UNION ALL SELECT 'Purchasing.PurchaseOrderLines', COUNT_BIG(*) FROM Purchasing.PurchaseOrderLines
  UNION ALL SELECT 'Warehouse.StockItems', COUNT_BIG(*) FROM Warehouse.StockItems
  UNION ALL SELECT 'Warehouse.StockItemHoldings', COUNT_BIG(*) FROM Warehouse.StockItemHoldings
  UNION ALL SELECT 'Application.People', COUNT_BIG(*) FROM Application.People
) counts
ORDER BY source_table
""")
    ranges = db.query_json("""
SELECT
  CONVERT(varchar(10), (SELECT MIN(OrderDate) FROM Sales.Orders), 23) AS sales_order_min_date,
  CONVERT(varchar(10), (SELECT MAX(OrderDate) FROM Sales.Orders), 23) AS sales_order_max_date,
  CONVERT(varchar(10), (SELECT MIN(OrderDate) FROM Purchasing.PurchaseOrders), 23) AS purchase_order_min_date,
  CONVERT(varchar(10), (SELECT MAX(OrderDate) FROM Purchasing.PurchaseOrders), 23) AS purchase_order_max_date,
  CAST(DATABASEPROPERTYEX(DB_NAME(), 'Version') AS varchar(20)) AS database_version
""")
    return {
        "table_counts": {row["source_table"]: row["record_count"] for row in counts},
        **ranges[0],
    }


def _canonical(source: dict[str, list[dict]]) -> dict[str, list[dict]]:
    product_by_id = {row["StockItemID"]: row for row in source["products"]}
    orgs: list[dict] = []
    for role, rows, id_key, name_key in (
        ("customer", source["customers"], "CustomerID", "CustomerName"),
        ("supplier", source["suppliers"], "SupplierID", "SupplierName"),
    ):
        for row in rows:
            source_id = row[id_key]
            orgs.append(
                {
                    "canonical_id": f"wwi:organization:{role}:{source_id}",
                    "source_system": "wwi",
                    "source_id": str(source_id),
                    "name": row[name_key],
                    "roles": role,
                    "primary_contact_source_id": row.get("PrimaryContactPersonID")
                    or "",
                    "phone": row.get("PhoneNumber") or "",
                    "website": row.get("WebsiteURL") or "",
                    "address_line_1": row.get("DeliveryAddressLine1") or "",
                    "address_line_2": row.get("DeliveryAddressLine2") or "",
                    "city": row.get("DeliveryCity") or "",
                    "state": row.get("DeliveryState") or "",
                    "country": row.get("DeliveryCountry") or "",
                    "postal_code": row.get("DeliveryPostalCode") or "",
                    "payment_days": row.get("PaymentDays") or "",
                    "credit_limit": _money(row.get("CreditLimit"))
                    if role == "customer"
                    else "",
                    "created_at": row.get("AccountOpenedDate")
                    or row.get("CreationDate")
                    or "",
                    "updated_at": row.get("LastUpdate") or "",
                    "data_class": "public_sample",
                }
            )
    person_organizations: dict[int, set[str]] = defaultdict(set)
    for role, rows, id_key in (
        ("customer", source["customers"], "CustomerID"),
        ("supplier", source["suppliers"], "SupplierID"),
    ):
        for row in rows:
            organization_id = f"wwi:organization:{role}:{row[id_key]}"
            for key in ("PrimaryContactPersonID", "AlternateContactPersonID"):
                if row.get(key):
                    person_organizations[int(row[key])].add(organization_id)
    for row in source["orders"]:
        if row.get("ContactPersonID"):
            person_organizations[int(row["ContactPersonID"])].add(
                f"wwi:organization:customer:{row['CustomerID']}"
            )
    for row in source["purchase_orders"]:
        if row.get("ContactPersonID"):
            person_organizations[int(row["ContactPersonID"])].add(
                f"wwi:organization:supplier:{row['SupplierID']}"
            )

    contacts = [
        {
            "canonical_id": f"wwi:contact:{row['PersonID']}",
            "source_system": "wwi",
            "source_id": str(row["PersonID"]),
            "full_name": row["FullName"],
            "preferred_name": row.get("PreferredName") or "",
            "email": row.get("EmailAddress") or "",
            "phone": row.get("PhoneNumber") or "",
            "company_canonical_id": (
                next(iter(person_organizations[int(row["PersonID"])]))
                if len(person_organizations[int(row["PersonID"])]) == 1
                else ""
            ),
            "is_employee": str(bool(row.get("IsEmployee"))).lower(),
            "is_salesperson": str(bool(row.get("IsSalesperson"))).lower(),
            "data_class": "public_sample",
        }
        for row in source["people"]
    ]
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
            "data_class": "public_sample",
        }
        for row in source["products"]
    ]
    sales_orders = [
        {
            "canonical_id": f"wwi:sales_order:{row['OrderID']}",
            "source_system": "wwi",
            "source_id": str(row["OrderID"]),
            "customer_canonical_id": f"wwi:organization:customer:{row['CustomerID']}",
            "contact_canonical_id": f"wwi:contact:{row['ContactPersonID']}",
            "salesperson_canonical_id": f"wwi:contact:{row['SalespersonPersonID']}",
            "order_date": _date(row["OrderDate"]),
            "expected_delivery_date": _date(row["ExpectedDeliveryDate"]),
            "customer_po_number": row.get("CustomerPurchaseOrderNumber") or "",
            "source_status": "picked" if row.get("PickingCompletedWhen") else "open",
            "data_class": "public_sample",
        }
        for row in source["orders"]
    ]
    sales_lines = []
    for row in source["sales_lines"]:
        quantity = Decimal(str(row["Quantity"]))
        picked = Decimal(str(row.get("PickedQuantity") or 0))
        unit_price = Decimal(str(row["UnitPrice"]))
        sales_lines.append(
            {
                "canonical_id": f"wwi:sales_order_line:{row['OrderLineID']}",
                "source_system": "wwi",
                "source_id": str(row["OrderLineID"]),
                "sales_order_canonical_id": f"wwi:sales_order:{row['OrderID']}",
                "product_canonical_id": f"wwi:product:{row['StockItemID']}",
                "description": row["Description"],
                "uom": product_by_id[row["StockItemID"]]["UnitPackage"],
                "ordered_quantity": _number(quantity),
                "delivered_quantity": _number(picked),
                "open_quantity": _number(max(quantity - picked, Decimal(0))),
                "unit_price_ex_tax": _money(unit_price),
                "tax_rate_percent": _number(row["TaxRate"]),
                "net_amount": _money(quantity * unit_price),
                "data_class": "public_sample",
            }
        )
    purchase_orders = [
        {
            "canonical_id": f"wwi:purchase_order:{row['PurchaseOrderID']}",
            "source_system": "wwi",
            "source_id": str(row["PurchaseOrderID"]),
            "supplier_canonical_id": f"wwi:organization:supplier:{row['SupplierID']}",
            "contact_canonical_id": f"wwi:contact:{row['ContactPersonID']}",
            "order_date": _date(row["OrderDate"]),
            "expected_delivery_date": _date(row["ExpectedDeliveryDate"]),
            "supplier_reference": row.get("SupplierReference") or "",
            "source_status": "finalized" if row.get("IsOrderFinalized") else "open",
            "data_class": "public_sample",
        }
        for row in source["purchase_orders"]
    ]
    purchase_lines = []
    for row in source["purchase_lines"]:
        product = product_by_id[row["StockItemID"]]
        factor = Decimal(str(product["QuantityPerOuter"]))
        ordered = Decimal(str(row["OrderedOuters"]))
        received = Decimal(str(row["ReceivedOuters"]))
        outer_price = Decimal(str(row["ExpectedUnitPricePerOuter"]))
        purchase_lines.append(
            {
                "canonical_id": f"wwi:purchase_order_line:{row['PurchaseOrderLineID']}",
                "source_system": "wwi",
                "source_id": str(row["PurchaseOrderLineID"]),
                "purchase_order_canonical_id": f"wwi:purchase_order:{row['PurchaseOrderID']}",
                "product_canonical_id": f"wwi:product:{row['StockItemID']}",
                "description": row["Description"],
                "source_uom": product["OuterPackage"],
                "canonical_uom": product["UnitPackage"],
                "units_per_outer": _number(factor),
                "ordered_outers": _number(ordered),
                "received_outers": _number(received),
                "open_quantity": _number(max(ordered - received, Decimal(0)) * factor),
                "expected_unit_price_per_outer": _money(outer_price),
                "expected_unit_price_each": _money(outer_price / factor),
                "last_receipt_date": _date(row.get("LastReceiptDate")),
                "data_class": "public_sample",
            }
        )
    return {
        "organizations": orgs,
        "contacts": contacts,
        "products": products,
        "sales_orders": sales_orders,
        "sales_order_lines": sales_lines,
        "purchase_orders": purchase_orders,
        "purchase_order_lines": purchase_lines,
    }


def _validate(canonical: dict[str, list[dict]]) -> list[dict]:
    errors: list[dict] = []
    keys = {
        name: {row["canonical_id"] for row in rows} for name, rows in canonical.items()
    }

    def require(entity: str, row: dict, fields: tuple[str, ...]) -> None:
        for field in fields:
            if row.get(field) in (None, ""):
                errors.append(
                    {
                        "entity": entity,
                        "source_id": row.get("source_id", ""),
                        "rule": "required",
                        "field": field,
                        "error": "value is required",
                    }
                )

    for row in canonical["organizations"]:
        require("organization", row, ("canonical_id", "name", "roles"))
    for row in canonical["contacts"]:
        require("contact", row, ("canonical_id", "full_name"))
    for row in canonical["products"]:
        require("product", row, ("canonical_id", "name", "uom", "units_per_outer"))
        if Decimal(row["units_per_outer"]) <= 0:
            errors.append(
                {
                    "entity": "product",
                    "source_id": row["source_id"],
                    "rule": "positive",
                    "field": "units_per_outer",
                    "error": "must be positive",
                }
            )
    for row in canonical["sales_orders"]:
        require(
            "sales_order", row, ("canonical_id", "customer_canonical_id", "order_date")
        )
        if row["customer_canonical_id"] not in keys["organizations"]:
            errors.append(
                {
                    "entity": "sales_order",
                    "source_id": row["source_id"],
                    "rule": "reference",
                    "field": "customer_canonical_id",
                    "error": "customer not extracted",
                }
            )
    for row in canonical["sales_order_lines"]:
        require(
            "sales_order_line",
            row,
            ("canonical_id", "sales_order_canonical_id", "product_canonical_id", "uom"),
        )
        if (
            row["sales_order_canonical_id"] not in keys["sales_orders"]
            or row["product_canonical_id"] not in keys["products"]
        ):
            errors.append(
                {
                    "entity": "sales_order_line",
                    "source_id": row["source_id"],
                    "rule": "reference",
                    "field": "parent/product",
                    "error": "reference not extracted",
                }
            )
        expected = Decimal(row["ordered_quantity"]) * Decimal(row["unit_price_ex_tax"])
        if abs(expected - Decimal(row["net_amount"])) > Decimal("0.01"):
            errors.append(
                {
                    "entity": "sales_order_line",
                    "source_id": row["source_id"],
                    "rule": "amount",
                    "field": "net_amount",
                    "error": "quantity × unit price mismatch",
                }
            )
    for row in canonical["purchase_orders"]:
        if row["supplier_canonical_id"] not in keys["organizations"]:
            errors.append(
                {
                    "entity": "purchase_order",
                    "source_id": row["source_id"],
                    "rule": "reference",
                    "field": "supplier_canonical_id",
                    "error": "supplier not extracted",
                }
            )
    for row in canonical["purchase_order_lines"]:
        if (
            row["purchase_order_canonical_id"] not in keys["purchase_orders"]
            or row["product_canonical_id"] not in keys["products"]
        ):
            errors.append(
                {
                    "entity": "purchase_order_line",
                    "source_id": row["source_id"],
                    "rule": "reference",
                    "field": "parent/product",
                    "error": "reference not extracted",
                }
            )
    return errors


def _scenarios(canonical: dict[str, list[dict]]) -> list[dict]:
    lines = canonical["sales_order_lines"]
    if not lines:
        return []
    order_date = max(
        date.fromisoformat(row["order_date"]) for row in canonical["sales_orders"]
    )
    deadline = order_date + timedelta(days=3)
    scenarios: list[dict] = []
    definitions = [
        ("F01", "stock_sufficient", "satisfiable"),
        ("F02", "on_time_inbound", "satisfiable"),
        ("F03", "late_inbound", "shortfall"),
        ("F04", "other_order_reservation", "shortfall"),
        ("F05", "partially_delivered", "satisfiable"),
        ("F06", "missing_inbound_date", "insufficient_information"),
    ]
    for index, (case_id, kind, expected) in enumerate(definitions):
        line = lines[index % len(lines)]
        demand = max(Decimal(line["ordered_quantity"]), Decimal(2))
        delivered = Decimal(0)
        on_hand = demand + 5
        reserved_other = Decimal(0)
        inbound = Decimal(0)
        inbound_date = ""
        if case_id == "F02":
            on_hand, inbound, inbound_date = (
                demand - 2,
                Decimal(2),
                (deadline - timedelta(days=1)).isoformat(),
            )
        elif case_id == "F03":
            on_hand, inbound, inbound_date = (
                demand - 2,
                Decimal(2),
                (deadline + timedelta(days=1)).isoformat(),
            )
        elif case_id == "F04":
            on_hand, reserved_other = demand, Decimal(1)
        elif case_id == "F05":
            delivered = (demand / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            on_hand = demand - delivered
        elif case_id == "F06":
            on_hand, inbound = demand - 2, Decimal(2)
        remaining = demand - delivered
        scenarios.append(
            {
                "case_id": case_id,
                "scenario_version": SCENARIO_VERSION,
                "scenario_type": kind,
                "derived_from": line["canonical_id"],
                "business_date": order_date.isoformat(),
                "timezone": "Europe/Berlin",
                "promise_scope": "ship_by",
                "promise_date": deadline.isoformat(),
                "warehouse": "WWI Main Warehouse",
                "product_canonical_id": line["product_canonical_id"],
                "uom": line["uom"],
                "ordered_quantity": _number(demand),
                "delivered_quantity": _number(delivered),
                "remaining_quantity": _number(remaining),
                "on_hand_quantity": _number(on_hand),
                "reserved_for_other_orders": _number(reserved_other),
                "current_order_in_reservations": "false",
                "unallocated_inbound_quantity": _number(inbound),
                "expected_inbound_date": inbound_date,
                "expected_result": expected,
                "data_class": "simulated",
            }
        )
    return scenarios


def _iso_utc(value: str) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (
        parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _normalized_domain(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host = (parsed.hostname or "").lower().removeprefix("www.").rstrip(".")
    return host.encode("idna").decode("ascii") if host else ""


def _twenty_company_rows(organizations: list[dict]) -> list[dict]:
    domains = [_normalized_domain(row.get("website", "")) for row in organizations]
    domain_counts = Counter(domain for domain in domains if domain)
    rows: list[dict] = []
    for organization, normalized_domain in zip(organizations, domains, strict=True):
        domain = normalized_domain if domain_counts[normalized_domain] == 1 else ""
        rows.append(
            {
                "Account Owner (ID)": "",
                "Address / Address 1": organization["address_line_1"],
                "Address / Address 2": organization["address_line_2"],
                "Address / City": organization["city"],
                "Address / State": organization["state"],
                "Address / Country": organization["country"],
                "Address / Post Code": organization["postal_code"],
                "Annual Revenue / Amount": "",
                "Annual Revenue / Currency": "",
                "Creation date": _iso_utc(organization["created_at"]),
                "Domain Name / Link URL": f"https://{domain}" if domain else "",
                "Domain Name / Link Label": domain,
                "Domain Name / Secondary Links": "[]",
                # The target UUID is assigned by Twenty and captured by API readback.
                # Leaving this blank avoids mapping two unique identifiers in one import.
                "Id": "",
                "Linkedin / Link URL": "",
                "Linkedin / Link Label": "",
                "Linkedin / Secondary Links": "[]",
                "Name": organization["name"],
                "WWI External ID": organization["canonical_id"],
                "Last update": _iso_utc(organization["updated_at"]),
            }
        )
    return rows


def _twenty_people_rows(contacts: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for contact in contacts:
        name_parts = contact["full_name"].strip().split(maxsplit=1)
        rows.append(
            {
                "First Name": name_parts[0] if name_parts else "",
                "Last Name": name_parts[1] if len(name_parts) > 1 else "",
                "Primary Email": contact["email"],
                "Primary Phone": contact["phone"],
                "Company WWI External ID": contact.get("company_canonical_id", ""),
                "WWI External ID": contact["canonical_id"],
            }
        )
    return rows


def _erpnext_uom(value: str) -> str:
    return ERPNEXT_UOM_MAP.get(value, value)


def _erpnext_customer_rows(customers: list[dict]) -> list[dict]:
    return [
        {
            "ID": "",
            "Customer Name": row["name"],
            "Customer Type": "Company",
            "Customer Group": "Commercial",
            "Territory": ERPNEXT_TERRITORY,
            "Operion Source Key": row["canonical_id"],
        }
        for row in customers
    ]


def _erpnext_supplier_rows(suppliers: list[dict]) -> list[dict]:
    return [
        {
            "ID": "",
            "Supplier Name": row["name"],
            "Supplier Type": "Company",
            "Supplier Group": "All Supplier Groups",
            "Operion Source Key": row["canonical_id"],
        }
        for row in suppliers
    ]


def _erpnext_item_rows(products: list[dict]) -> list[dict]:
    return [
        {
            "ID": "",
            "Item Code": row["canonical_id"],
            "Item Name": row["name"],
            "Item Group": "Products",
            "Default Unit of Measure": _erpnext_uom(row["uom"]),
            "Maintain Stock": 1,
            "Standard Selling Rate": row["unit_price_ex_tax"],
            "Operion Source Key": row["canonical_id"],
        }
        for row in products
    ]


def _erpnext_contact_rows(
    contacts: list[dict],
    organizations_by_id: dict[str, dict],
) -> list[dict]:
    rows: list[dict] = []
    for contact in contacts:
        name_parts = contact["full_name"].strip().split(maxsplit=1)
        organization = organizations_by_id.get(contact.get("company_canonical_id", ""))
        link_doctype = ""
        link_name = ""
        if organization:
            link_doctype = (
                "Customer" if organization["roles"] == "customer" else "Supplier"
            )
            link_name = organization["name"]
        rows.append(
            {
                "ID": "",
                "First Name": name_parts[0] if name_parts else "",
                "Last Name": name_parts[1] if len(name_parts) > 1 else "",
                "Operion Source Key": contact["canonical_id"],
                "Email ID (Email IDs)": contact["email"],
                "Is Primary (Email IDs)": "1" if contact["email"] else "",
                "Number (Contact Numbers)": contact["phone"],
                "Is Primary Phone (Contact Numbers)": "1" if contact["phone"] else "",
                "Link Document Type (Links)": link_doctype,
                "Link Name (Links)": link_name,
            }
        )
    return rows


def _blank_parent(headers: list[str], first_child_header: str) -> dict:
    first_child_index = headers.index(first_child_header)
    return {header: "" for header in headers[:first_child_index]}


def _erpnext_sales_order_rows(
    orders: list[dict],
    lines: list[dict],
    organizations_by_id: dict[str, dict],
    products_by_id: dict[str, dict],
) -> list[dict]:
    lines_by_order: dict[str, list[dict]] = defaultdict(list)
    for line in lines:
        if Decimal(line["open_quantity"]) > 0:
            lines_by_order[line["sales_order_canonical_id"]].append(line)
    rows: list[dict] = []
    for order in orders:
        order_lines = lines_by_order.get(order["canonical_id"], [])
        if not order_lines:
            continue
        for index, line in enumerate(order_lines):
            product = products_by_id[line["product_canonical_id"]]
            quantity = Decimal(line["open_quantity"])
            rate = Decimal(line["unit_price_ex_tax"])
            amount = _money(quantity * rate)
            parent = (
                {
                    "ID": "",
                    "Series": "SAL-ORD-.YYYY.-",
                    "Customer": organizations_by_id[order["customer_canonical_id"]][
                        "name"
                    ],
                    "Order Type": "Sales",
                    "Date": order["order_date"],
                    "Delivery Date": order["expected_delivery_date"],
                    "Company": ERPNEXT_COMPANY,
                    "Currency": ERPNEXT_CURRENCY,
                    "Exchange Rate": "1",
                    "Price List": "Standard Selling",
                    "Price List Currency": ERPNEXT_CURRENCY,
                    "Price List Exchange Rate": "1",
                    "Customer's Purchase Order": order["customer_po_number"],
                    "Operion Source Key": order["canonical_id"],
                    "WWI Source Status": order["source_status"],
                }
                if index == 0
                else _blank_parent(ERPNEXT_SALES_ORDER_HEADERS, "Item Code (Items)")
            )
            rows.append(
                {
                    **parent,
                    "Item Code (Items)": line["product_canonical_id"],
                    "Item Name (Items)": product["name"],
                    "Delivery Date (Items)": order["expected_delivery_date"],
                    "Quantity (Items)": _number(quantity),
                    "Stock UOM (Items)": _erpnext_uom(line["uom"]),
                    "UOM (Items)": _erpnext_uom(line["uom"]),
                    "UOM Conversion Factor (Items)": "1",
                    "Rate (Items)": _money(rate),
                    "Amount (Items)": amount,
                    "Basic Rate (Company Currency) (Items)": _money(rate),
                    "Amount (Company Currency) (Items)": amount,
                    "Operion Source Key (Items)": line["canonical_id"],
                }
            )
    return rows


def _erpnext_purchase_order_rows(
    orders: list[dict],
    lines: list[dict],
    organizations_by_id: dict[str, dict],
    products_by_id: dict[str, dict],
) -> list[dict]:
    lines_by_order: dict[str, list[dict]] = defaultdict(list)
    for line in lines:
        if Decimal(line["open_quantity"]) > 0:
            lines_by_order[line["purchase_order_canonical_id"]].append(line)
    rows: list[dict] = []
    for order in orders:
        order_lines = lines_by_order.get(order["canonical_id"], [])
        if not order_lines:
            continue
        for index, line in enumerate(order_lines):
            product = products_by_id[line["product_canonical_id"]]
            quantity = Decimal(line["open_quantity"])
            rate = Decimal(line["expected_unit_price_each"])
            amount = _money(quantity * rate)
            parent = (
                {
                    "ID": "",
                    "Series": "PUR-ORD-.YYYY.-",
                    "Supplier": organizations_by_id[order["supplier_canonical_id"]][
                        "name"
                    ],
                    "Date": order["order_date"],
                    "Required By": order["expected_delivery_date"],
                    "Company": ERPNEXT_COMPANY,
                    "Currency": ERPNEXT_CURRENCY,
                    "Exchange Rate": "1",
                    "Price List": "Standard Buying",
                    "Price List Currency": ERPNEXT_CURRENCY,
                    "Price List Exchange Rate": "1",
                    "Operion Source Key": order["canonical_id"],
                    "WWI Supplier Reference": order["supplier_reference"],
                    "WWI Source Status": order["source_status"],
                }
                if index == 0
                else _blank_parent(ERPNEXT_PURCHASE_ORDER_HEADERS, "Item Code (Items)")
            )
            rows.append(
                {
                    **parent,
                    "Item Code (Items)": line["product_canonical_id"],
                    "Item Name (Items)": product["name"],
                    "Required By (Items)": order["expected_delivery_date"],
                    "Quantity (Items)": _number(quantity),
                    "Stock UOM (Items)": _erpnext_uom(line["canonical_uom"]),
                    "UOM (Items)": _erpnext_uom(line["canonical_uom"]),
                    "UOM Conversion Factor (Items)": "1",
                    "Rate (Items)": _money(rate),
                    "Amount (Items)": amount,
                    "Rate (Company Currency) (Items)": _money(rate),
                    "Amount (Company Currency) (Items)": amount,
                    "Operion Source Key (Items)": line["canonical_id"],
                }
            )
    return rows


def _exports(canonical: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    customers = [
        row for row in canonical["organizations"] if row["roles"] == "customer"
    ]
    suppliers = [
        row for row in canonical["organizations"] if row["roles"] == "supplier"
    ]
    organizations_by_id = {
        row["canonical_id"]: row for row in canonical["organizations"]
    }
    products_by_id = {row["canonical_id"]: row for row in canonical["products"]}
    erpnext = {
        "customers": _erpnext_customer_rows(customers),
        "suppliers": _erpnext_supplier_rows(suppliers),
        "items": _erpnext_item_rows(canonical["products"]),
        "contacts": _erpnext_contact_rows(canonical["contacts"], organizations_by_id),
        "sales_orders": _erpnext_sales_order_rows(
            canonical["sales_orders"],
            canonical["sales_order_lines"],
            organizations_by_id,
            products_by_id,
        ),
        "purchase_orders": _erpnext_purchase_order_rows(
            canonical["purchase_orders"],
            canonical["purchase_order_lines"],
            organizations_by_id,
            products_by_id,
        ),
    }
    twenty = {
        "companies": _twenty_company_rows(canonical["organizations"]),
        "people": _twenty_people_rows(canonical["contacts"]),
    }
    return {"erpnext": erpnext, "twenty": twenty}


def _identity_map(canonical: dict[str, list[dict]], batch_id: str) -> list[dict]:
    entity_targets = {
        "organizations": ("erpnext", "twenty"),
        "contacts": ("erpnext", "twenty"),
        "products": ("erpnext",),
        "sales_orders": ("erpnext",),
        "sales_order_lines": ("erpnext",),
        "purchase_orders": ("erpnext",),
        "purchase_order_lines": ("erpnext",),
    }
    eligible_ids = {
        entity: {record["canonical_id"] for record in canonical[entity]}
        for entity in entity_targets
    }
    for prefix in ("sales", "purchase"):
        line_entity = f"{prefix}_order_lines"
        order_entity = f"{prefix}_orders"
        parent_field = f"{prefix}_order_canonical_id"
        eligible_lines = {
            record["canonical_id"]
            for record in canonical[line_entity]
            if Decimal(record["open_quantity"]) > 0
        }
        eligible_orders = {
            record[parent_field]
            for record in canonical[line_entity]
            if record["canonical_id"] in eligible_lines
        }
        eligible_ids[line_entity] = eligible_lines
        eligible_ids[order_entity] = eligible_orders

    rows = []
    for entity, targets in entity_targets.items():
        for record in canonical[entity]:
            for target in targets:
                included = record["canonical_id"] in eligible_ids[entity]
                rows.append(
                    {
                        "entity_type": entity.rstrip("s"),
                        "source_system": "wwi",
                        "source_id": record["source_id"],
                        "canonical_id": record["canonical_id"],
                        "target_system": target,
                        "target_id": "",
                        "batch_id": batch_id,
                        "mapping_version": MAPPING_VERSION,
                        "load_status": "pending" if included else "not_applicable",
                        "error": "" if included else "excluded: no open commitment",
                    }
                )
    return rows


def run_etl(
    snapshot_dir: Path,
    batch_id: str,
    data_root: Path = Path("data"),
    reports_root: Path = Path("reports"),
    container: str = "enterprise-demo-mssql",
    order_limit: int = 8,
) -> Path:
    source_manifest_path = snapshot_dir / "source_manifest.json"
    backup_path = snapshot_dir / "WideWorldImporters-Full.bak"
    if not source_manifest_path.is_file() or not backup_path.is_file():
        raise FileNotFoundError(
            "Snapshot must contain source_manifest.json and the WWI backup"
        )
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if sha256_file(backup_path) != source_manifest["sha256"]:
        raise RuntimeError("Source backup does not match its recorded checksum")

    roots = [
        data_root / "canonical" / batch_id,
        data_root / "exports" / "erpnext" / batch_id,
        data_root / "exports" / "twenty" / batch_id,
        data_root / "quarantine" / batch_id,
        reports_root / batch_id,
    ]
    for root in roots:
        if root.exists():
            raise FileExistsError(f"Refusing to overwrite batch output: {root}")

    started = datetime.now(UTC)
    db = SqlServer(container)
    source_profile = _source_profile(db)
    source = _extract(db, order_limit)
    canonical = _canonical(source)
    errors = _validate(canonical)
    scenarios = _scenarios(canonical)
    canonical["fulfillment_scenarios"] = scenarios
    exports = _exports(canonical)
    identity = _identity_map(canonical, batch_id)

    canonical_dir, erpnext_dir, twenty_dir, quarantine_dir, report_dir = roots
    for entity, rows in canonical.items():
        _write_csv(canonical_dir / f"{entity}.csv", rows)
    erpnext_headers = {
        "customers": ERPNEXT_CUSTOMER_HEADERS,
        "suppliers": ERPNEXT_SUPPLIER_HEADERS,
        "items": ERPNEXT_ITEM_HEADERS,
        "contacts": ERPNEXT_CONTACT_HEADERS,
        "sales_orders": ERPNEXT_SALES_ORDER_HEADERS,
        "purchase_orders": ERPNEXT_PURCHASE_ORDER_HEADERS,
    }
    for name, rows in exports["erpnext"].items():
        _write_csv(erpnext_dir / f"{name}.csv", rows, erpnext_headers[name], "\n")
    for name, rows in exports["twenty"].items():
        if name == "companies":
            _write_csv(twenty_dir / f"{name}.csv", rows, TWENTY_COMPANY_HEADERS, "\n")
        elif name == "people":
            _write_csv(twenty_dir / f"{name}.csv", rows, TWENTY_PEOPLE_HEADERS, "\n")
        else:
            _write_csv(twenty_dir / f"{name}.csv", rows)
    _write_csv(report_dir / "identity_map.csv", identity)
    error_fields = ["entity", "source_id", "rule", "field", "error"]
    _write_csv(quarantine_dir / "errors.csv", errors, error_fields)

    completed = datetime.now(UTC)
    manifest = {
        "batch_id": batch_id,
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "source_snapshot": str(snapshot_dir),
        "source_sha256": source_manifest["sha256"],
        "source_data_class": source_manifest["usage_class"],
        "mapping_version": MAPPING_VERSION,
        "scenario_version": SCENARIO_VERSION,
        "target_versions": {"erpnext": "16.34.2", "twenty": "2.39.0"},
        "target_mapping_assumptions": {
            "erpnext_company": ERPNEXT_COMPANY,
            "erpnext_currency": ERPNEXT_CURRENCY,
            "currency_note": "WWI source monetary fields have no explicit currency; numeric amounts are mapped to the demo company's EUR currency",
            "uom": ERPNEXT_UOM_MAP,
            "territory": ERPNEXT_TERRITORY,
            "purchase_order_scope": "open commitments only; exclude zero-open-quantity lines and their completed parent orders",
        },
        "selection": {
            "strategy": "latest sales orders plus recent purchase orders sharing selected products",
            "sales_order_limit": order_limit,
        },
        "source_profile": source_profile,
        "record_counts": {name: len(rows) for name, rows in canonical.items()},
        "export_counts": {
            system: {name: len(rows) for name, rows in files.items()}
            for system, files in exports.items()
        },
        "identity_map_rows": len(identity),
        "validation": {
            "status": "passed" if not errors else "failed",
            "error_count": len(errors),
        },
        "load_status": "not_loaded",
        "rerun_policy": "immutable batch directories; use identity_map stable keys and target readback before load",
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise RuntimeError(
            f"ETL validation failed with {len(errors)} error(s); see {quarantine_dir}"
        )
    return report_dir
