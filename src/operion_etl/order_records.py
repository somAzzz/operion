import json
import re
from uuid import UUID

from . import complaint
from .identity_readback import (
    ERPNextReadClient,
    IdentityReadbackError,
    TwentyReadClient,
)

READ_ERRORS = (IdentityReadbackError, OSError, ValueError, KeyError, TypeError)


def erp_order(client: ERPNextReadClient, order: str, owner: str, company: str) -> dict:
    key = "custom_operion_source_key"
    rows = client.http.get_json(
        "/api/resource/Sales%20Order",
        {
            "fields": json.dumps(["name", key, "customer", "company"]),
            "filters": json.dumps({key: order, "company": company}),
            "limit_page_length": 2,
        },
    )["data"]
    if rows == []:
        return {"status": "no_match"}
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("ambiguous ERPNext order")
    row = rows[0]
    if row[key] != order or row["company"] != company or not row["customer"]:
        raise ValueError("ERPNext order relationship mismatch")
    customer = client.record("Customer", row["customer"])
    if customer["name"] != row["customer"] or customer[key] != owner:
        raise ValueError("ERPNext customer relationship mismatch")
    name = row["name"]
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or re.search(r"[/\\\x00-\x1f]", name)
    ):
        raise ValueError("invalid ERPNext document name")
    return {"status": "verified", "id": name, "label": name}


def crm_contact(client: TwentyReadClient, company_id: str, contact: str) -> dict:
    page = client.http.get_json(
        "/rest/people", {"filter": f"wwiExternalId[eq]:{contact}", "limit": 2}
    )
    people = page["data"]["people"]
    if people == [] and page["totalCount"] == 0:
        return {"status": "no_match"}
    if len(people) != 1 or page["totalCount"] != 1:
        raise ValueError("ambiguous order contact")
    person = people[0]
    if person["wwiExternalId"] != contact or person["companyId"] != company_id:
        raise ValueError("order contact relationship mismatch")
    name = person["name"]
    if not isinstance(name, dict):
        raise ValueError("invalid CRM person name")
    label = " ".join(filter(None, (name.get("firstName"), name.get("lastName"))))
    return {
        "status": "verified",
        "id": str(UUID(person["id"])),
        "label": label or "Open Twenty order contact",
    }


def order_contact(client: TwentyReadClient, context: dict, contact: str | None) -> dict:
    if not context["has_linked_person"] or not contact:
        return {"status": "no_match"}
    try:
        return crm_contact(client, context["company_id"], contact)
    except READ_ERRORS:
        return {"status": "unavailable"}


def resolve(
    *,
    order: str,
    owner: str,
    contact: str | None,
    company: str,
    erp: ERPNextReadClient | None,
    crm: TwentyReadClient | None,
) -> dict:
    records = {
        kind: {"status": "not_configured"}
        for kind in ("sales_order", "company", "person")
    }
    if erp:
        try:
            records["sales_order"] = erp_order(erp, order, owner, company)
        except READ_ERRORS:
            records["sales_order"] = {"status": "unavailable"}
    if crm:
        try:
            context = complaint.customer_context(crm, owner)
        except READ_ERRORS:
            context = {"status": "unavailable"}
        if context["status"] == "mapped":
            company_id = context["company_id"]
            records["company"] = {
                "status": "verified",
                "id": company_id,
                "label": context["company"],
            }
            records["person"] = order_contact(crm, context, contact)
        else:
            status = (
                "no_match" if context["status"] == "no_crm_mapping" else "unavailable"
            )
            records["company"] = {"status": status}
            records["person"] = {"status": status}
    return records
