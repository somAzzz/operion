"""Fixed English labels and safe formatting for server-owned business evidence."""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .answer_evidence import EvidenceContext

LABELS = {
    "invoice_id": "Invoice ID",
    "customer_count": "Customers",
    "customers_with_orders": "Customers with sales orders",
    "sales_order_count": "Sales orders",
    "purchase_order_count": "Purchase orders",
    "open_order_count": "Open sales orders (source open or natively confirmed)",
    "page_order_count": "Orders returned on this page",
    "page_customer_count": "Customers represented on this page",
    "result_count": "Matching records",
    "canonical_id": "Canonical ID",
    "customer_id": "Customer ID",
    "supplier_id": "Supplier ID",
    "organization_id": "Organization ID",
    "name": "Name",
    "full_name": "Full name",
    "customer_name": "Customer",
    "supplier_name": "Supplier",
    "organization_name": "Organization",
    "city": "City",
    "country": "Country",
    "order_number": "Order number",
    "order_date": "Order date",
    "expected_delivery_date": "Expected delivery date",
    "net_total_ex_tax": "Net total excluding tax",
    "unit_price_ex_tax": "Unit price excluding tax",
    "net_amount": "Line net amount",
    "currency": "Currency",
    "business_status": "Business status",
    "source_status": "Source status",
    "docstatus": "Native document status",
    "source_system": "Source system",
    "order_count": "Sales orders for this customer",
    "email": "Email",
    "phone": "Phone",
    "email_state": "Email evidence state",
    "phone_state": "Phone evidence state",
    "target_id": "Target record ID",
    "twenty_id": "Twenty ID",
    "erpnext_id": "ERPNext ID",
    "mapping_status": "Mapping status",
    "product_id": "Product ID",
    "product_name": "Product",
    "description": "Description",
    "uom": "Unit",
    "ordered_quantity": "Ordered quantity",
    "picked_quantity": "Picked quantity",
    "delivered_quantity": "Delivered quantity",
    "base_quantity": "Base quantity",
    "quantity": "Quantity",
    "unpicked_quantity": "Unpicked quantity",
    "delivery_date": "Delivery date",
    "remaining_quantity": "Remaining quantity",
    "on_hand_quantity": "On-hand quantity",
    "reserved_quantity": "Reserved for other orders",
    "available_quantity": "Available now",
    "inbound_quantity": "Unallocated inbound quantity",
    "usable_inbound_quantity": "Inbound usable by promise date",
    "shortfall_quantity": "Shortfall quantity",
    "result": "Snapshot fulfillment result",
    "case_id": "Scenario ID",
    "promise_date": "Promise date",
    "warehouse": "Warehouse",
    "authorization": "Operation authorization",
    "execution": "Operation execution",
    "resolution": "Resolution",
    "action_id": "Proposal ID",
    "state": "Proposal state",
}


def escape_cell(value: Any) -> str:
    # Source names can contain malicious Markdown and HTML
    value = str(value).replace("\n", " ").replace("\r", " ")
    for symbol in ("\\", "|", "`", "*", "_", "[", "]", "(", ")", "#", "!"):
        value = value.replace(symbol, "\\" + symbol)
    return html.escape(value, quote=False)


def label(field: str) -> str:
    return LABELS[field]


COVERAGE_LABELS = {
    "portfolio_current_dataset": "current authorized dataset",
    "filtered_total": "filtered total",
    "entity_filtered_total": "total for this organization",
    "returned_page": "returned page",
    "entity": "record evidence",
    "capability_only": "capability only; no operation executed",
    "proposal_only_not_executed": "proposal only; not executed",
    "snapshot_scenario_only": "snapshot scenario only",
}
TABLE_LABELS = {
    "fulfillment quantities": "Snapshot fulfillment quantities",
    "sales orders": "Sales orders",
    "purchase orders": "Purchase orders",
    "customers": "Order counts by customer",
    "customer": "Customer",
    "supplier": "Supplier",
    "organization": "Organization",
    "order": "Order",
    "contact": "Contact",
    "contacts": "Contacts",
    "lines": "Order lines",
    "results": "Search results",
    "candidates": "Matching candidates",
}
DEFAULT_COLUMNS = {
    "sales orders": (
        "canonical_id",
        "customer_name",
        "order_number",
        "order_date",
        "currency",
        "net_total_ex_tax",
        "business_status",
        "source_status",
    ),
    "purchase orders": (
        "canonical_id",
        "supplier_name",
        "order_number",
        "order_date",
        "currency",
        "net_total_ex_tax",
        "business_status",
        "source_status",
    ),
}


def context_text(ctx: EvidenceContext) -> str:
    mode = {
        "snapshot": "Snapshot",
        "live": "Upstream read",
        "unknown": "Source mode unknown",
    }.get(ctx.data_mode, "Source mode unknown")
    completeness = {
        "complete": "complete",
        "partial": "partial; more records may exist",
        "not_assessed": "not assessed",
    }.get(ctx.completeness, "not assessed")
    filter_labels = {
        "limit": "Page size",
        "max_orders": "Maximum returned orders",
        "customer": "Customer",
        "customer_id": "Customer",
        "supplier": "Supplier",
        "supplier_id": "Supplier",
        "date_from": "From",
        "date_to": "To",
        "status": "Status",
        "query": "Search",
        "name": "Name",
        "order_id": "Order",
        "case_id": "Scenario",
        "operation": "Operation",
        "relationship": "Relationship",
        "customer_query": "Customer search",
    }
    filters = []
    for key, value in json.loads(ctx.filters).items():
        if value is None:
            continue
        if key == "cursor":
            filters.append("Following page")
        elif key in filter_labels:
            if key == "customer" and value == "*":
                value = "All authorized customers"
            filters.append(f"{filter_labels[key]}: {escape_cell(value)}")
        else:
            filters.append("Additional conditions in source evidence")
    filters = "; ".join(filters) or "No additional filters"
    warning_labels = {
        "source_stale": "Source observation may be stale",
        "source_snapshot_skew": "Source observation times differ",
        "frozen_fulfillment_snapshot": "Frozen fulfillment scenario",
    }
    warnings = "; ".join(
        warning_labels.get(w, "Additional source limitation")
        for w in ctx.warnings
        if w != "snapshot_not_live"
    )
    return (
        f"E{ctx.call_index} · {mode} · Business date: {escape_cell(ctx.business_date)}. Scope: current dataset and server-authorized records. Result completeness: {completeness}. Filters: {filters}. This does not establish full source history or real-time state."
        + (f" Source warnings: {warnings}." if warnings else "")
    )
