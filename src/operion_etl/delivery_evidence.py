"""Frozen WWI invoice observations; no live delivery or line receipt semantics."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Invoice(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    invoice_id: int = Field(gt=0)
    invoice_order_id: int
    invoice_customer_id: int
    credit_note: bool
    confirmed_at: str | None
    has_recipient: bool


class OrderInvoices(BaseModel):
    linked_invoice_count: int = Field(ge=0, strict=True)
    customer_id: str
    invoices: list[Invoice]


class Slice(BaseModel):
    snapshot_id: Literal["interview-wwi-delivery-v1"]
    extracted_at: AwareDatetime
    orders_sha256: str
    orders: dict[str, OrderInvoices]


FILE = "delivery-evidence-v1.json"


def investigate(directory: Path, detail: dict) -> dict:
    snapshot = Slice.model_validate_json((directory / FILE).read_bytes())
    if (
        snapshot.orders_sha256
        != hashlib.sha256((directory / "sales_orders.csv").read_bytes()).hexdigest()
    ):
        raise ValueError("order slice mismatch")
    order = detail["order"]
    subject = order["canonical_id"]
    entry = snapshot.orders[subject]
    owner = order["customer_id"]
    if len(entry.invoices) != entry.linked_invoice_count:
        raise ValueError("incomplete invoice slice")
    if entry.customer_id != owner:
        raise ValueError("order customer mismatch")
    expected = date.fromisoformat(order["expected_delivery_date"])
    invoices = []
    invoice_ids = [
        i.invoice_id for group in snapshot.orders.values() for i in group.invoices
    ]
    if len(invoice_ids) != len(set(invoice_ids)):
        raise ValueError("non-unique source invoice ID")
    for i in entry.invoices:
        if (
            subject != f"wwi:sales_order:{i.invoice_order_id}"
            or owner != f"wwi:organization:customer:{i.invoice_customer_id}"
        ):
            raise ValueError("invalid invoice relationship")
        confirmation = (
            datetime.fromisoformat(i.confirmed_at) if i.confirmed_at else None
        )
        offset = (
            (confirmation.date() - expected).days
            if confirmation and not i.credit_note
            else None
        )
        invoices.append(
            {
                **i.model_dump(),
                "source_record_id": f"Sales.Invoices:{i.invoice_id}",
                "source_field": "ReturnedDeliveryData.DeliveredWhen",
                "confirmation_status": "recorded" if confirmation else "not_available",
                "subject_ref": f"wwi:invoice:{i.invoice_id}",
                "granularity": "invoice",
                "calendar_days_from_expected": offset,
                "derivation": [
                    "Sales.Orders.ExpectedDeliveryDate",
                    "Sales.Invoices.ConfirmedDeliveryTime",
                ]
                if offset is not None
                else [],
            }
        )
    return {
        "contract_version": "delivery-investigation-v1",
        "order_id": subject,
        "customer_id": owner,
        "expected_date": expected.isoformat(),
        "invoices": invoices,
        "lookup": "linked_invoices" if invoices else "no_linked_invoice",
        "lines": [
            {
                k: r[k]
                for k in ("canonical_id", "ordered_quantity", "picked_quantity", "uom")
            }
            for r in detail["lines"]
        ],
        "line_receipt": "not_evidenced",
        "carrier_responsibility": "not_evidenced",
        "next_step": "verify_line_level_receipt",
        "snapshot_id": snapshot.snapshot_id,
        "extracted_at": snapshot.extracted_at.isoformat(),
        "data_mode": "snapshot",
        "business_date": detail["business_date"],
        "source_observed_at": detail["source_observed_at"],
        "completeness": {
            "status": "complete",
            "scope": "linked_invoices_in_pinned_snapshot",
        },
    }


def card_rows(data: dict, request: str) -> list[tuple[str]]:
    rows = []
    if request:
        rows.append((f"User statement / request (unverified): {request}",))
    order, expected = data["order_id"], data["expected_date"]
    rows.append((f"Order {order}; expected date {expected}.",))
    if not data["invoices"]:
        rows.append(("No linked invoice in this WWI slice.",))
    for i in data["invoices"]:
        ref, ts = i["source_record_id"], i["confirmed_at"]
        kind = "Credit note" if i["credit_note"] else "Invoice"
        rows.append((f"{kind} {ref}: recorded confirmation: {ts or 'not available'}.",))
        days = i["calendar_days_from_expected"]
        if days is not None:
            relation = "after" if days > 0 else "before" if days < 0 else "on"
            rows.append(
                (
                    f"{ref}: confirmation date {relation} expected date ({abs(days)} calendar {'day' if abs(days) == 1 else 'days'}).",
                )
            )
    for line in data["lines"]:
        ident, qty, picked, unit = (
            line[k]
            for k in ("canonical_id", "ordered_quantity", "picked_quantity", "uom")
        )
        rows.append(
            (f"{ident}: ordered {qty} {unit}; picked {picked or 'unknown'} {unit}.",)
        )
    rows.extend(
        [
            (
                "Not established: actual arrival, quantity received per line, or carrier responsibility. A later confirmation does not disprove a report of non-receipt on the expected date.",
            ),
            (
                "Next: verify the itemized receipt or warehouse discrepancy record before replying.",
            ),
            (
                f"Historical WWI snapshot {data['snapshot_id']}; extracted {data['extracted_at']}.",
            ),
        ]
    )
    return rows
