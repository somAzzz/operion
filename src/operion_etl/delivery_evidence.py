"""WWI delivery observations and order-scoped investigation cards."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from . import complaint


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
    snapshot_id: Literal["demo-wwi-delivery-v1", "interview-wwi-delivery-v1"]
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
    if len(entry.invoices) != entry.linked_invoice_count:
        raise ValueError("incomplete invoice slice")
    if entry.customer_id != order["customer_id"]:
        raise ValueError("order customer mismatch")
    invoice_ids = [
        i.invoice_id for group in snapshot.orders.values() for i in group.invoices
    ]
    if len(invoice_ids) != len(set(invoice_ids)):
        raise ValueError("non-unique source invoice ID")
    return build_investigation(
        subject,
        order["customer_id"],
        order["expected_delivery_date"],
        detail["lines"],
        entry.invoices,
        {
            "snapshot_id": snapshot.snapshot_id,
            "extracted_at": snapshot.extracted_at.isoformat(),
            "data_mode": "snapshot",
            "business_date": detail["business_date"],
            "source_observed_at": detail["source_observed_at"],
            "completeness": {
                "status": "complete",
                "scope": "linked_invoices_in_pinned_snapshot",
            },
        },
    )


def build_investigation(
    subject: str,
    owner: str,
    expected_date: str,
    lines: list,
    linked_invoices: list[Invoice],
    metadata: dict,
) -> dict:
    expected = date.fromisoformat(expected_date)
    invoices = []
    for i in linked_invoices:
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
            for r in lines
        ],
        "line_receipt": "not_evidenced",
        "carrier_responsibility": "not_evidenced",
        "next_step": "verify_line_level_receipt",
        **metadata,
    }


def date_comparison_requested(request: str) -> bool:
    return bool(
        re.search(
            r"\b(?:compar\w*|difference|how many days|on time|early|late)\b",
            request,
            re.I,
        )
        and re.search(r"\b(?:dates?|expected|scheduled)\b", request, re.I)
        and not re.search(
            r"\b(?:quantity|units?|items?|receiv\w*|stock|warehouse|supplier|purchase|draft|reply|complaint)\b",
            request,
            re.I,
        )
    )


def _reported_nonreceipt_on(note: dict, expected: date) -> bool:
    day = f"{expected:%B} {expected.day}"
    return bool(
        re.match(
            rf"^(?:Our warehouse reported that nothing arrived|We received nothing) on {day}(?:,? {expected.year})?[.]",
            note["claim"],
            re.I,
        )
    )


def card_rows(
    data: dict, request: str, record_links: dict | None = None
) -> list[tuple[str]]:
    rows = []
    note = data.get("complaint")
    dates_only = not note and date_comparison_requested(request)
    if note:
        rows.extend(complaint.evidence_rows(note))
    else:
        reported = re.search(r"\bcustomer reports? ([^.!?]+)", request, re.I)
        if reported:
            rows.append((f"Reported customer statement (unverified): {reported[1]}.",))
    crm = {} if dates_only else data.get("crm", {})
    if crm.get("status") == "mapped" and not note:
        contact_status = crm.get("order_contact", {}).get("status")
        if contact_status == "verified":
            contact_text = "Order contact verified."
        elif contact_status == "unavailable":
            contact_text = "Order contact lookup unavailable."
        elif crm["has_linked_person"]:
            contact_text = "Order contact pending confirmation."
        else:
            contact_text = "Contact pending confirmation (no linked Twenty Person)."
        rows.append((f"Twenty company: {crm['company']}. {contact_text}",))
    elif crm.get("status") == "no_crm_mapping":
        rows.append(
            (
                "No matching Twenty company for this WWI customer. Contact pending confirmation.",
            )
        )
    elif crm.get("status") == "source_unavailable":
        rows.append(
            (
                "CRM context unavailable. Customer mapping and contact could not be verified.",
            )
        )
    order, expected = data["order_id"], data["expected_date"]
    rows.append((f"Order {order}; expected date {expected}.",))
    if not data["invoices"]:
        rows.append(
            (
                "No linked invoice returned by WWI SQL Server."
                if data["data_mode"] == "live"
                else "No linked invoice in this WWI slice.",
            )
        )
    for i in data["invoices"]:
        ref, ts = i["source_record_id"], i["confirmed_at"]
        kind = "Credit note" if i["credit_note"] else "Invoice"
        if record_links is not None and data["data_mode"] == "live":
            record_links[len(rows)] = ("invoice", i["invoice_id"])
        rows.append((f"{kind} {ref}: recorded confirmation: {ts or 'not available'}.",))
        days = i["calendar_days_from_expected"]
        if days is not None:
            relation = "after" if days > 0 else "before" if days < 0 else "on"
            if dates_only:
                rows[-1] = (
                    f"{kind} {ref}: confirmation recorded at {ts}, {relation} expected date ({abs(days)} calendar {'day' if abs(days) == 1 else 'days'}).",
                )
                continue
            rows.append(
                (
                    f"{ref}: confirmation date {relation} expected date ({abs(days)} calendar {'day' if abs(days) == 1 else 'days'}).",
                )
            )
    linked = {str(i["invoice_id"]) for i in data["invoices"]}
    cited = re.findall(r"\binvoice\s+(?:number\s+)?#?([0-9]+)\b", request, re.I)
    for invoice_id in sorted(set(cited) - linked):
        rows.append(
            (
                f"Invoice {invoice_id} is absent from the linked invoices for this order and cannot support this investigation.",
            )
        )
    observed = (
        f"WWI SQL Server query time (UTC): {data['queried_at']}."
        if data["data_mode"] == "live"
        else f"Historical WWI snapshot {data['snapshot_id']}; extracted {data['extracted_at']}."
    )
    if dates_only:
        return [*rows, ("Actual arrival time is unknown.",), (observed,)]
    for line in data["lines"]:
        ident, qty, picked, unit = (
            line[k]
            for k in ("canonical_id", "ordered_quantity", "picked_quantity", "uom")
        )
        rows.append(
            (
                f"{ident}: ordered {qty} {unit}; picked {picked if picked is not None and picked != '' else 'unknown'} {unit}.",
            )
        )
    for issue in data.get("issues", []):
        if record_links is not None and data["data_mode"] == "live":
            record_links[len(rows)] = ("issue", issue["issue_id"])
        rows.append(
            (
                f"Stock issue {issue['issue_id']} · invoice {issue['invoice_id']} · item {issue['stock_item_id']}: warehouse posted {abs(Decimal(issue['quantity'])).normalize():f} units out at {issue['issued_at']}.",
            )
        )
    if data.get("issues"):
        rows.append(
            (
                "Purchase source unverified. See the stock issue for prior receipts of the same item. A lot allocation or reservation linking receipt to issue is required to identify the source.",
            )
        )
    rows.append(
        (
            "Not established: actual arrival, quantity received per line, or carrier responsibility.",
        )
    )
    if note and _reported_nonreceipt_on(note, date.fromisoformat(expected)):
        for invoice in data["invoices"]:
            if (invoice["calendar_days_from_expected"] or 0) > 0:
                confirmed = invoice["confirmed_at"][:10]
                rows.append(
                    (
                        f"The customer reports non-receipt on {expected}. Invoice {invoice['invoice_id']} records confirmation on {confirmed}. These observations concern different dates and can both be true.",
                    )
                )
    rows.append(("Next: verify the itemized receipt or warehouse discrepancy record.",))
    rows.append((observed,))
    if note:
        confirmations = [
            i for i in data["invoices"] if i["confirmed_at"] and not i["credit_note"]
        ]
        draft = [
            "Thank you for letting us know. We checked the records for your order.",
        ]
        for issue in data["issues"]:
            draft.append(
                f"Our warehouse recorded {abs(Decimal(issue['quantity'])).normalize():f} units of item {issue['stock_item_id']} as issued on {issue['issued_at'][:10]}."
            )
        for invoice in confirmations:
            draft.append(
                f"The delivery confirmation in our system is dated {invoice['confirmed_at'][:10]}."
            )
        draft.append(
            "We cannot yet confirm how many units your warehouse received. We will check the itemized receipt with our warehouse team."
        )
        rows.append((" ".join(draft),))
    return rows
