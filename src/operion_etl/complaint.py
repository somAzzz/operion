import re
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from .identity_readback import TwentyReadClient

CUSTOMER = "wwi:organization:customer:65"
ORDER = "66823"
NOTE_ID = str(uuid5(NAMESPACE_URL, "operion/interview/66823/complaint"))
TARGET_ID = str(uuid5(NAMESPACE_URL, "operion/interview/66823/complaint/company"))
TITLE = "Simulated customer complaint | WWI order 66823"
PERSON_TARGET_ID = str(uuid5(NAMESPACE_URL, "operion/interview/66823/complaint/sender"))
NOTE_REF = re.compile(
    r"\bnote\s+(?:id\s+)?([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b", re.I
)


def customer_context(client: TwentyReadClient, customer_id: str) -> dict:
    page = client.http.get_json(
        "/rest/companies", {"filter": f"wwiExternalId[eq]:{customer_id}", "limit": 2}
    )
    companies = page["data"]["companies"]
    if page["totalCount"] == 0 and companies == []:
        return {"status": "no_crm_mapping", "customer_id": customer_id}
    if (
        len(companies) != 1
        or page["totalCount"] != 1
        or companies[0]["wwiExternalId"] != customer_id
    ):
        raise ValueError("ambiguous CRM customer mapping")
    company = companies[0]
    company_id = str(UUID(company["id"]))
    people = client.http.get_json(
        "/rest/people", {"filter": f"companyId[eq]:{company_id}", "limit": 1}
    )
    linked = people["data"]["people"]
    if bool(linked) != bool(people["totalCount"]) or any(
        p["companyId"] != company_id for p in linked
    ):
        raise ValueError("CRM contact relationship mismatch")
    return {
        "status": "mapped",
        "customer_id": customer_id,
        "company_id": company_id,
        "company": company["name"],
        "has_linked_person": bool(linked),
    }


class ComplaintOutsideScope(Exception):
    pass


def read_complaint(
    client: TwentyReadClient, note_id: str, customers: frozenset[str]
) -> dict:
    note_id = str(UUID(note_id))
    get = client.http.get_json
    page = get("/rest/noteTargets", {"filter": f"noteId[eq]:{note_id}", "limit": 20})
    targets = page["data"]["noteTargets"]
    if len(targets) != page["totalCount"] or any(
        t["noteId"] != note_id for t in targets
    ):
        raise ValueError("incomplete complaint relationships")
    companies = [t["targetCompanyId"] for t in targets if t.get("targetCompanyId")]
    if not companies:
        raise ComplaintOutsideScope
    if len(companies) != 1:
        raise ValueError("ambiguous complaint company")
    company_id = str(UUID(companies[0]))
    record = get(f"/rest/companies/{company_id}")["data"]["company"]
    owner = record.get("wwiExternalId")
    if record["id"] != company_id or owner not in customers:
        raise ComplaintOutsideScope
    company = customer_context(client, owner)
    if company.get("company_id") != company_id:
        raise ValueError("complaint company mapping mismatch")
    note = get(f"/rest/notes/{note_id}")["data"]["note"]
    order = re.fullmatch(
        r"Simulated customer complaint \| WWI order ([1-9][0-9]{0,9})", note["title"]
    )
    if note["id"] != note_id or not order:
        raise ValueError("unsupported complaint note")
    body = note["bodyV2"]["markdown"]
    envelope = re.fullmatch(r"From: ([^\s<>@]+@[^\s<>@]+)\n\n(.+)", body, re.S)
    address, claim = envelope.groups() if envelope else (None, body)
    if not claim.strip():
        raise ValueError("missing complaint text")
    people = [t["targetPersonId"] for t in targets if t.get("targetPersonId")]
    sender = {"status": "unconfirmed"}
    if address and len(people) == 1:
        person_id = str(UUID(people[0]))
        person = get(f"/rest/people/{person_id}")["data"]["person"]
        if (
            person["id"] == person_id
            and person["companyId"] == company_id
            and (person.get("emails", {}).get("primaryEmail") or "").casefold()
            == address.casefold()
        ):
            name = " ".join(
                filter(
                    None,
                    (person["name"].get("firstName"), person["name"].get("lastName")),
                )
            )
            if name:
                sender = {
                    "status": "verified",
                    "id": person_id,
                    "external_id": person.get("wwiExternalId"),
                    "name": name,
                    "email": address,
                }
    return {
        "contract_version": "complaint-context-v1",
        "data_mode": "live",
        "source_observed_at": datetime.now(UTC).isoformat(),
        "note_id": note_id,
        "title": note["title"],
        "claim": claim,
        "channel": "simulated_email" if envelope else "note",
        "sender": sender,
        "company_id": company_id,
        "company": company["company"],
        "crm": company,
        "customer_id": owner,
        "order_id": order[1],
    }


def evidence_rows(note: dict) -> list[tuple[str]]:
    sender = note["sender"]
    identity = (
        f"CRM sender: {sender['name']} ({sender['email']})."
        if sender["status"] == "verified"
        else "Complaint sender pending confirmation."
    )
    channel = (
        "Simulated customer email"
        if note["channel"] == "simulated_email"
        else "Customer note"
    )
    return [
        (
            f"{channel} · Twenty Note {note['note_id']} · order reference {note['order_id']}.",
        ),
        (f"{identity} Company: {note['company']}.",),
        (f"Customer statement (unverified): {note['claim']}",),
        (f"CRM read time (UTC): {note['source_observed_at']}.",),
    ]
