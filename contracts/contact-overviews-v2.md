# Contact overviews v2

This is the current contract for `get_customer_overview` and
`get_supplier_overview`. The E1 v1 contract records the earlier minimum-test
field restrictions and is retained as historical acceptance evidence.

## Scope and fields

The service resolves one customer or supplier within the server-defined canonical
scope before returning contacts. Each contact may include its canonical and target
IDs, name, relationship or preferred name, email, and phone. Email and phone are
returned as recorded; an empty value means the selected source has no nonempty
value. Credit limit, payment terms, notes, and arbitrary source fields remain
outside the response. Search results, order lists, and errors do not expose contact
details.

Snapshot mode returns email and phone only for contacts classified as
`public_sample` or `simulated`. It labels the result as a snapshot. Other data
classes require a separate field-authorization decision under E5.1.

Live customer overviews read Person email and phone from Twenty and verify the
Person's Company ID against the resolved customer. Live supplier overviews read
the ERPNext Contact detail, select its primary email and phone, and verify both
its canonical source key and Supplier link. A failed read or mismatched relation
returns `source_unavailable`; canonical snapshot contact details are never used
as a live fallback.

## Cross-system interpretation

The canonical ID joins the authorized roster to target records. A contact's
presence in the snapshot does not prove that it was imported into either target.
Likewise, a missing email or phone in one target does not prove it is missing in
the other. The overview reports the fields from the source named above and keeps
its observation mode and source metadata visible.

These overviews are read-only. The E1 authorization, ambiguity, pagination,
source-failure, and no-write controls remain in force. Field access for real
enterprise data is not enabled by this demo contract.
