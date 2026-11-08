"""Provision the public interview Company, simulated Note and its Company link."""

import csv
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import NAMESPACE_URL, uuid5

from operion_etl.complaint import (
    CUSTOMER,
    NOTE_ID,
    PERSON_TARGET_ID,
    TARGET_ID,
    TITLE,
    read_complaint,
)
from operion_etl.identity_readback import (
    TwentyReadClient,
    read_identity_map,
    write_identity_map,
)
from operion_etl.twenty import TwentyClient, read_env

CLAIM = "Our warehouse reported that nothing arrived on February 18. We have an invoice and would like you to check whether all 48 units were received before you reply."


def main():
    env = read_env()
    base = env.get("TWENTY_API_BASE_URL", "http://127.0.0.1:3000")
    admin = TwentyClient(base, env["TWENTY_API_KEY"])
    reader = TwentyReadClient(base, env["TWENTY_API_KEY_READ_ONLY"])
    with Path("data/canonical/interview-wwi-v1/organizations.csv").open() as stream:
        row = next(r for r in csv.DictReader(stream) if r["canonical_id"] == CUSTOMER)
    companies = reader.records("companies")
    matches = [c for c in companies if c["wwiExternalId"] == CUSTOMER]
    if not matches:
        if any(c["name"] == row["name"] for c in companies):
            raise ValueError("existing company needs identity reconciliation")
        admin.create_company(
            {
                "id": str(uuid5(NAMESPACE_URL, CUSTOMER)),
                "name": row["name"],
                "wwiExternalId": CUSTOMER,
            }
        )
        matches = [
            c for c in reader.records("companies") if c["wwiExternalId"] == CUSTOMER
        ]
    if len(matches) != 1 or matches[0]["name"] != row["name"]:
        raise ValueError("WWI company mapping is ambiguous or inconsistent")
    company = matches[0]
    people = [
        p
        for p in reader.records("people")
        if p.get("wwiExternalId") == "wwi:contact:1129"
    ]
    if len(people) != 1 or people[0]["companyId"] != company["id"]:
        raise ValueError("simulated sender mapping is missing or ambiguous")
    sender = people[0]
    address = sender["emails"]["primaryEmail"]
    if address != "hanuman@tailspintoys.com":
        raise ValueError("simulated sender address mismatch")
    body = f"From: {address}\n\n{CLAIM}"
    notes = reader.records("notes")
    if not any(n["id"] == NOTE_ID for n in notes):
        if any(n["title"] == TITLE for n in notes):
            raise ValueError("existing complaint needs identity reconciliation")
        admin.graphql(
            "mutation($data: NoteCreateInput!) { createNote(data:$data){id} }",
            {"data": {"id": NOTE_ID, "title": TITLE, "bodyV2": {"markdown": body}}},
        )
    else:
        existing = next(n for n in notes if n["id"] == NOTE_ID)
        if existing["title"] != TITLE or existing["bodyV2"]["markdown"] not in (
            CLAIM,
            body,
        ):
            raise ValueError("existing demo note needs reconciliation")
        if existing["bodyV2"]["markdown"] == CLAIM:
            admin.graphql(
                "mutation($id: UUID!, $data: NoteUpdateInput!) { updateNote(id:$id, data:$data){id} }",
                {"id": NOTE_ID, "data": {"bodyV2": {"markdown": body}}},
            )
    targets = [t for t in reader.records("noteTargets") if t["noteId"] == NOTE_ID]
    if not any(t.get("targetCompanyId") for t in targets):
        admin.graphql(
            "mutation($data: NoteTargetCreateInput!) { createNoteTarget(data:$data){id} }",
            {
                "data": {
                    "id": TARGET_ID,
                    "targetCompanyId": company["id"],
                    "noteId": NOTE_ID,
                }
            },
        )
    if not any(t.get("targetPersonId") for t in targets):
        admin.graphql(
            "mutation($data: NoteTargetCreateInput!) { createNoteTarget(data:$data){id} }",
            {
                "data": {
                    "id": PERSON_TARGET_ID,
                    "noteId": NOTE_ID,
                    "targetPersonId": sender["id"],
                }
            },
        )
    result = read_complaint(reader, NOTE_ID, frozenset({CUSTOMER}))
    if result["sender"].get("id") != sender["id"]:
        raise ValueError("complaint sender readback failed")
    destination = Path("var/interview-demo/wwi-direct-identity-map.csv")
    baseline = Path("reports/interview-wwi-v1/identity_map.csv")
    mappings = read_identity_map(destination if destination.exists() else baseline)
    (binding,) = (
        m
        for m in mappings
        if m["canonical_id"] == CUSTOMER and m["target_system"] == "twenty"
    )
    if binding["source_id"] != "65" or binding["target_id"] not in ("", company["id"]):
        raise ValueError("existing identity map needs reconciliation")
    binding.update(target_id=company["id"], load_status="loaded", error="")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as temp:
        staging = Path(temp.name)
    try:
        write_identity_map(staging, mappings)
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)
    print(
        f"Verified {result['company']} ({CUSTOMER}), Company {company['id']}, Note {NOTE_ID}"
    )


if __name__ == "__main__":
    main()
