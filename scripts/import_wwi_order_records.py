"""Import the authorized WWI interview sales orders into the local demo systems."""

import argparse
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import NAMESPACE_URL, uuid5

from operion_etl.e2_data import ERPNextAdminClient
from operion_etl.identity_readback import (
    ERPNextReadClient,
    TwentyReadClient,
    read_identity_map,
    write_identity_map,
)
from operion_etl.interview_demo import _existing_mismatches
from operion_etl.interview_wwi import CUSTOMER_ORDER_COUNTS
from operion_etl.sqlserver import SqlServer
from operion_etl.twenty import TwentyClient, read_env

COMPANY = "AI Demo GmbH"
KEY = "custom_operion_source_key"
LINE_KEY = "custom_operion_source_key_items"


def extract():
    ids = ",".join(str(i) for i in sorted(CUSTOMER_ORDER_COUNTS))
    db = SqlServer()
    customers = db.query_json(f"""
        SELECT c.CustomerID, c.CustomerName, p.PersonID, p.FullName, p.EmailAddress
        FROM Sales.Customers c JOIN Application.People p ON p.PersonID=c.PrimaryContactPersonID
        WHERE c.CustomerID IN ({ids}) ORDER BY c.CustomerID""")
    orders = db.query_json(f"""
        SELECT OrderID, CustomerID, ContactPersonID, OrderDate, ExpectedDeliveryDate, CustomerPurchaseOrderNumber
        FROM Sales.Orders WHERE CustomerID IN ({ids}) ORDER BY CASE WHEN OrderID=66823 THEN 0 ELSE 1 END, OrderID""")
    lines = db.query_json(f"""
        SELECT l.OrderID,l.OrderLineID,l.StockItemID,s.StockItemName, l.Description,l.Quantity,l.UnitPrice,
               p.PackageTypeName AS uom,b.PackageTypeName AS base_uom
        FROM Sales.OrderLines l JOIN Sales.Orders o ON o.OrderID=l.OrderID
        JOIN Warehouse.StockItems s ON s.StockItemID=l.StockItemID
        JOIN Warehouse.PackageTypes p ON p.PackageTypeID=l.PackageTypeID
        JOIN Warehouse.PackageTypes b ON b.PackageTypeID=s.UnitPackageID
        WHERE o.CustomerID IN ({ids}) ORDER BY l.OrderID,l.OrderLineID""")
    contacts = {c["CustomerID"]: c["PersonID"] for c in customers}
    if set(contacts) != set(CUSTOMER_ORDER_COUNTS) or len(orders) != 1197:
        raise ValueError("unexpected authorized WWI order population")
    if any(contacts[o["CustomerID"]] != o["ContactPersonID"] for o in orders):
        raise ValueError("order contact differs from the customer relationship")
    if (
        len(lines) != 3581
        or {line["OrderID"] for line in lines} != {o["OrderID"] for o in orders}
        or any(line["uom"] != line["base_uom"] for line in lines)
    ):
        raise ValueError("incomplete order or incompatible package units")
    return customers, orders, lines


def unique_index(records, field):
    index = {}
    for row in records:
        key = row.get(field)
        if key:
            if key in index:
                raise ValueError(f"duplicate external ID {key}")
            index[key] = row
    return index


def save_verified_targets(targets):
    dest = Path("var/interview-demo/wwi-direct-identity-map.csv")
    template = Path("reports/interview-wwi-v1/identity_map.csv")
    records = read_identity_map(dest if dest.exists() else template)
    indexed = {(r["target_system"], r["canonical_id"]): r for r in records}
    for (system, key), target in targets.items():
        row = indexed.setdefault(
            (system, key),
            {
                "target_system": system,
                "canonical_id": key,
                "source_system": "wwi",
                "source_id": key.split(":")[-1],
                "entity_type": key.split(":")[1],
                "batch_id": "wwi-direct",
                "mapping_version": "interview-wwi-v1.2",
            },
        )
        if row.get("target_id") and row["target_id"] != target:
            raise ValueError(f"conflicting verified mapping for {system} {key}")
        row.update(target_id=target, load_status="loaded", error="")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        temp = Path(tmp.name)
    try:
        write_identity_map(temp, list(indexed.values()))
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)


def transfer(apply):
    customers, orders, lines = extract()
    env = read_env()
    erp_url, crm_url = "http://localhost:8080", "http://localhost:3000"
    er = ERPNextReadClient(erp_url, env["ERPNEXT_API_KEY_READ_ONLY"])
    cr = TwentyReadClient(crm_url, env["TWENTY_API_KEY_READ_ONLY"])
    ew = ERPNextAdminClient(erp_url, env["ERPNEXT_API_KEY"]) if apply else None
    cw = TwentyClient(crm_url, env["TWENTY_API_KEY"]) if apply else None
    stats = Counter()
    targets = {}
    if er.record("Company", COMPANY)["default_currency"] != "EUR":
        raise ValueError("expected EUR company")
    erp_index = {
        dt: unique_index(er.records(dt, ["name", KEY]), KEY)
        for dt in ("Customer", "Contact", "Item", "Sales Order")
    }

    def ensure_erp(dt, payload):
        key = payload[KEY]
        match = erp_index[dt].get(key)
        if match:
            name = match["name"]
        elif ew:
            name = ew.create(dt, payload)["name"]
            stats[f"{dt} created"] += 1
        else:
            raise ValueError(f"missing {dt} {key}")
        doc = er.record(dt, name)
        mismatch = _existing_mismatches(dt, doc, payload)
        if mismatch:
            raise ValueError(f"{dt} {key} conflicts on {mismatch}")
        if dt == "Sales Order":
            expected = sum(
                Decimal(str(i["qty"])) * Decimal(str(i["rate"]))
                for i in payload["items"]
            )
            if (
                doc["contact_person"] != payload["contact_person"]
                or Decimal(str(doc["net_total"])) != expected
            ):
                raise ValueError(f"{key} contact or net total differs")
            for item in doc["items"]:
                targets[("erpnext", item[LINE_KEY])] = item["name"]
        targets[("erpnext", key)] = name
        erp_index[dt][key] = {"name": name}
        stats[f"{dt} verified"] += 1
        return name

    companies = unique_index(cr.records("companies"), "wwiExternalId")
    people = unique_index(cr.records("people"), "wwiExternalId")
    buyer = {}
    contact = {}
    for row in customers:
        cid, pid = row["CustomerID"], row["PersonID"]
        ck, pk = f"wwi:organization:customer:{cid}", f"wwi:contact:{pid}"
        name = row["CustomerName"]
        first, _, last = row["FullName"].partition(" ")
        if ck not in companies and cw:
            cw.create_company(
                {"id": str(uuid5(NAMESPACE_URL, ck)), "wwiExternalId": ck, "name": name}
            )
        company = cr.http.get_json(
            "/rest/companies", {"filter": f"wwiExternalId[eq]:{ck}", "limit": 2}
        )
        if (
            company["totalCount"] != 1
            or company["data"]["companies"][0]["name"] != name
        ):
            raise ValueError(f"unverified Twenty Company {ck}")
        comp = company["data"]["companies"][0]
        if pk not in people and cw:
            cw.create_person(
                {
                    "id": str(uuid5(NAMESPACE_URL, pk)),
                    "wwiExternalId": pk,
                    "companyId": comp["id"],
                    "name": {"firstName": first, "lastName": last},
                    "emails": {
                        "primaryEmail": row["EmailAddress"],
                        "additionalEmails": [],
                    },
                }
            )
        page = cr.http.get_json(
            "/rest/people", {"filter": f"wwiExternalId[eq]:{pk}", "limit": 2}
        )
        if page["totalCount"] != 1:
            raise ValueError(f"unverified Twenty Person {pk}")
        person = page["data"]["people"][0]
        if (
            comp["wwiExternalId"] != ck
            or person["wwiExternalId"] != pk
            or person["companyId"] != comp["id"]
            or person["name"] != {"firstName": first, "lastName": last}
        ):
            raise ValueError(f"unverified CRM customer/contact relationship {ck}")
        targets[("twenty", ck)] = comp["id"]
        targets[("twenty", pk)] = person["id"]
        stats["CRM customer/contact pairs verified"] += 1
        buyer[cid] = ensure_erp(
            "Customer",
            {
                KEY: ck,
                "customer_name": name,
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Rest Of The World",
            },
        )
        contact[pid] = ensure_erp(
            "Contact",
            {
                KEY: pk,
                "first_name": first,
                "last_name": last,
                "links": [{"link_doctype": "Customer", "link_name": buyer[cid]}],
                "email_ids": [{"email_id": row["EmailAddress"], "is_primary": 1}],
            },
        )

    units = {r["name"] for r in er.records("UOM", ["name"])}
    items = {}
    grouped = defaultdict(list)
    for line in lines:
        iid = line["StockItemID"]
        uom = "Unit" if line["uom"] == "Each" else line["uom"]
        if uom not in units:
            if not ew:
                raise ValueError(f"missing UOM {uom}")
            ew.create("UOM", {"uom_name": uom, "must_be_whole_number": 1})
            units.add(uom)
        if iid not in items:
            key = f"wwi:product:{iid}"
            payload = {
                KEY: key,
                "item_name": line["StockItemName"],
                "stock_uom": uom,
                "is_stock_item": 1,
            }
            if key not in erp_index["Item"]:
                payload.update(item_code=key, item_group="Products")
            items[iid] = ensure_erp("Item", payload)
        grouped[line["OrderID"]].append(
            {
                "item_code": items[iid],
                "description": line["Description"],
                LINE_KEY: f"wwi:sales_order_line:{line['OrderLineID']}",
                "qty": line["Quantity"],
                "uom": uom,
                "conversion_factor": 1,
                "rate": line["UnitPrice"],
                "amount": str(Decimal(str(line["UnitPrice"])) * line["Quantity"]),
            }
        )
    for year in sorted({row["OrderDate"][:4] for row in orders}):
        existing = er.http.get_json(
            "/api/resource/Fiscal%20Year",
            {
                "fields": json.dumps(
                    ["name", "year_start_date", "year_end_date", "disabled"]
                ),
                "filters": json.dumps({"year_start_date": year + "-01-01"}),
            },
        )["data"]
        if not existing and ew:
            ew.create(
                "Fiscal Year",
                {
                    "year": year,
                    "year_start_date": year + "-01-01",
                    "year_end_date": year + "-12-31",
                    "companies": [{"company": COMPANY}],
                },
            )
        elif (
            len(existing) != 1
            or existing[0]["disabled"]
            or existing[0]["year_end_date"] != year + "-12-31"
        ):
            raise ValueError(f"missing or conflicting fiscal year {year}")
    for index, row in enumerate(orders, 1):
        oid = row["OrderID"]
        ensure_erp(
            "Sales Order",
            {
                KEY: f"wwi:sales_order:{oid}",
                "customer": buyer[row["CustomerID"]],
                "company": COMPANY,
                "contact_person": contact[row["ContactPersonID"]],
                "transaction_date": row["OrderDate"],
                "delivery_date": row["ExpectedDeliveryDate"],
                "currency": "EUR",
                "conversion_rate": 1,
                "selling_price_list": "Standard Selling",
                "po_no": row["CustomerPurchaseOrderNumber"],
                "docstatus": 0,
                "items": [
                    dict(i, delivery_date=row["ExpectedDeliveryDate"])
                    for i in grouped[oid]
                ],
            },
        )
        if index == 1 or index % 100 == 0:
            print(f"{index}/{len(orders)} sales orders verified", flush=True)
    stats["sales order lines verified"] = len(lines)
    if apply:
        save_verified_targets(targets)
    print(json.dumps(stats, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="insert missing local demo records; default is read-only verification",
    )
    transfer(parser.parse_args().apply)
