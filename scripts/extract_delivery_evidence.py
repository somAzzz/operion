"""Extract the public WWI interview delivery sidecar from the restored source."""

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from operion_etl.sqlserver import SqlServer

DIRECTORY = Path("data/canonical/interview-wwi-v1")


def main():
    orders_path = DIRECTORY / "sales_orders.csv"
    with orders_path.open() as stream:
        expected = {int(r["source_id"]): r for r in csv.DictReader(stream)}
    if len(expected) != 30:
        raise ValueError("expected the original 30-order WWI interview slice")
    rows = SqlServer().query_json(f"""
        SELECT o.OrderID AS order_id, o.CustomerID AS customer_id,
               COUNT(i.InvoiceID) OVER(PARTITION BY o.OrderID) AS linked_invoice_count,
               o.ExpectedDeliveryDate AS expected_date, i.InvoiceID AS invoice_id,
               i.OrderID AS invoice_order_id, i.CustomerID AS invoice_customer_id,
               i.IsCreditNote AS credit_note, i.ConfirmedDeliveryTime AS confirmed_at,
               CAST(CASE WHEN NULLIF(i.ConfirmedReceivedBy,'') IS NULL THEN 0
                         ELSE 1 END AS bit) AS has_recipient
        FROM Sales.Orders o LEFT JOIN Sales.Invoices i ON i.OrderID=o.OrderID
        WHERE o.OrderID IN ({",".join(str(i) for i in sorted(expected))})
        ORDER BY o.OrderID, i.InvoiceID""")
    orders = {}
    for r in rows:
        row = expected[r["order_id"]]
        owner = f"wwi:organization:customer:{r['customer_id']}"
        if (
            owner != row["customer_canonical_id"]
            or r["expected_date"] != row["expected_delivery_date"]
        ):
            raise ValueError("source order does not match the pinned selection")
        entry = orders.setdefault(
            row["canonical_id"],
            {
                "customer_id": owner,
                "linked_invoice_count": r["linked_invoice_count"],
                "invoices": [],
            },
        )
        if r["invoice_id"] is not None:
            entry["invoices"].append(
                {
                    k: r[k]
                    for k in (
                        "invoice_id",
                        "invoice_order_id",
                        "invoice_customer_id",
                        "credit_note",
                        "confirmed_at",
                        "has_recipient",
                    )
                }
            )
    if len(orders) != len(expected):
        raise ValueError("incomplete source query")
    result = {
        "snapshot_id": "interview-wwi-delivery-v1",
        "orders_sha256": hashlib.sha256(orders_path.read_bytes()).hexdigest(),
        "extracted_at": datetime.now(UTC).isoformat(),
        "orders": orders,
    }
    destination = DIRECTORY / "delivery-evidence-v1.json"
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(result, indent=2) + "\n")
    temp.replace(destination)


if __name__ == "__main__":
    main()
