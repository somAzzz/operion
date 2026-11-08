# WWI order delivery investigation

Ask the demo Agent: **“Order 66823: our warehouse says nothing arrived on the 18th. Was it late, and did all 48 units arrive?”** The final investigation card in chat quotes the request as unverified, compares dates, lists picking evidence, identifies what remains unknown and suggests checking the itemized receipt. The investigation does not change a business record.

Agent function calling and the independent stdio MCP server expose the same read-only capability, `get_order_delivery_evidence(order_id)`, for any WWI sales order in the authenticated customer scope. In direct mode the SQL procedure applies both the order ID and the authorized customers. The ten demo customers cover 1,197 orders. The 30-order catalog is the frozen regression scope. The MCP result is structured evidence; the Agent presents it through its existing verified Markdown answer path.

## Run the Web investigation

From the repository root, with restored WWI, local SGLang and a built Web app:

```bash
uv sync --frozen --all-extras
scripts/setup-wwi-delivery-reader.sh
.venv/bin/python scripts/seed_delivery_complaint.py
scripts/demo.sh start-wwi
```

Open [the local evidence desk](http://127.0.0.1:3100/) and click **Read customer email**. The Agent calls the independent, read-only `get_complaint_context(note_id)` capability shared with MCP. It reads the Note, checks the Company external ID against the authorized customers and matches the simulated From address to the linked Person in that Company. An absent, ambiguous or mismatched Person leaves the sender unconfirmed. Notes use a reported order reference in their title. A delivery follow-up verifies the order and its owner through WWI. A direct order inquiry also supports customers with no CRM mapping. One parameterized call reads the order, lines, linked invoices, stock issues and up to two prior authorized receipts per issue. The card shows the SQL query time in UTC and each invoice's recorded confirmation time in its original source clock. The WWI sample contains historical business records.

The seed operation checks the exact WWI external ID before creating the Company. It upgrades the known simulated Note to an email with a From header and links its sender through a Person NoteTarget. The runtime reads Twenty with a read-only credential. The original Twenty exports cover eight WWI customers and two suppliers, with no customer 65. Its Company now uses `wwi:organization:customer:65`. Provisioning scripts run separately from the read-only Agent. Note and NoteTarget IDs are deterministic so a retry can complete a partial setup without duplicating the complaint. The Agent receives only the read-only Twenty key. The seed writes the verified source ID 65 and Company UUID to the local direct profile identity map. The 30-order fixtures and their prepared identity map remain reproducible.

**Order record links.** Clicking a sales order number in a conversation opens the verified ERPNext document in a new tab. This lookup uses only the ERP record mapping. The separate records link opens the local [order 66823 records](http://127.0.0.1:3100/orders/66823) page. Each request checks the signed-in customer scope. The ERPNext link requires the sales order's external key, operating company and customer mapping. The Twenty Person must match both the WWI order's ContactPersonID and its verified Company. A missing or unverifiable relationship has no external link. The target systems apply their own session permissions. For non-local deployments, configure browser-reachable origins in `OPERION_ERPNEXT_WEB_URL` and `OPERION_TWENTY_WEB_URL` on the Web service.

In the demo, expand the first tool call to show the Twenty-only lookup. In the same conversation ask whether the delivery confirmation contradicts the email. The server can reuse the CRM observation and its original read time from the last verified answer in the authenticated conversation and scope. The delivery call reads WWI for that customer and order. The card links to the complaint, Company, verified order contact and ERP order, and includes a reply draft for human review. If WWI cannot be queried, the answer repeats the attributed CRM statement and reports that delivery evidence is unknown. A new inquiry starts without the previous complaint binding.

Stock issue 305669 belongs to invoice 64067. Receipt 305626 belongs to purchase order 1904. Receipt 305233 for purchase order 1902 is another earlier receipt of the same item. Receipt context is filtered by supplier permissions inside SQL. WWI supplies no allocation between these inbound and outbound postings. The evidence card always marks that relationship as unverified.

The SQL login `operion_delivery_reader` receives EXECUTE on the single read procedure. The local provisioning script needs Docker access once. The running Agent and MCP connect over TCP using the password file, with no Docker or administrator credential. Configure `OPERION_WWI_HOST`, `OPERION_WWI_PORT` and `OPERION_WWI_PASSWORD_FILE` for a different connection.

A missing credential, failed connection or failed query returns `source_unavailable`. A complete query with no linked invoices returns `no_linked_invoice`. A missing scoped order returns an order lookup error. Direct mode never consults the delivery sidecar. An explicitly selected `OPERION_DELIVERY_SOURCE=snapshot` or `scripts/demo.sh start-wwi-snapshot` uses the pinned regression evidence.

If the investigation has a failed SQL query for the bound order and no conflicting outcome, the server sends a status-only plan through the normal answer verifier without another model decision. The Web answer states that delivery evidence could not be queried and that invoice and confirmation existence remain unknown. A Twenty lookup failure, a malformed record, or a failed lookup for another order does not establish this SQL status.

For the optional Compose gateway, provision the reader, create an internal Docker network named `operion-wwi-delivery`, and attach the WWI container to that network with alias `wwi-sql`. Layer [the delivery override](../deploy/gateway/compose.wwi-delivery.yaml) on the gateway Compose file. Only the Agent receives the reader secret and the database network. Other business capabilities keep their configured data sources.

**Snapshot regression scope.** [The versioned extract](../data/canonical/demo-wwi-v1/delivery-evidence-v1.json) covers the 30 original sales orders, including explicitly empty matches, bound to the original order CSV by SHA-256. Every invoice must match the resolved order and customer. Preserve separate invoices, including credit notes. Confirmation time and the presence of a recipient come from the same source JSON; recipient names are not exported. Extraction time is not delivery time. Source datetime values are compared as recorded calendar dates, without inventing a time zone.

**Results.** A complete empty result means no linked invoice in the queried source for this order. An ordinary invoice can have or lack confirmation; a credit note cannot produce a delivery-date finding. An inaccessible order does not disclose whether it exists. Source failure, invalid relationships, missing coverage, or incomplete rows produce an error, never a negative finding. A recorded confirmation does not prove physical arrival time, line-level receipt, or fault.

**Publication.** The model selects a whole investigation card. It cannot edit its cells or publish only its favorable half. The case is about one order per turn: use an explicit reference such as “order 66823” or “order number 66823”. Invoice references from a different order are invalid even for authorized records retrieved in the same run. A direct order inquiry must explicitly name one order. A complaint inquiry may also use the order reference from its scoped Twenty Note, including the dated CRM observation in the previous verified answer. If it is missing or ambiguous, restate the order number. Automatically rendered error statuses must belong to the same investigation. Model routing remains subject to evaluation; these checks apply when the investigation capability is used.

**Replay from the repository root:**

```bash
# Regenerate only when refreshing the pinned public source (requires restored WWI).
PYTHONPATH=src .venv/bin/python scripts/extract_delivery_evidence.py
# Offline cases; T04 uses synthetic timestamps, T05 removes a temporary copy.
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_delivery_investigation.py -v
# Direct SQL: same-customer T03, closed-port failure, and on-source T01/T02.
OPERION_TEST_WWI_SQLSERVER=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_wwi_delivery_reader -v
# Include real Twenty coverage, the 66823 complaint and the attempted PO attribution.
OPERION_TEST_DELIVERY_COMPLAINT=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_delivery_complaint -v
# Snapshot, local SGLang, temporary conversation store, real AG-UI endpoint.
PYTHONPATH=src .venv/bin/python scripts/accept_delivery_investigation.py
```

T01: order 66823 / invoice 64067, confirmation one day after expected, line receipt unknown.
T02: order 73279, no linked invoice. T03: invoice 33513 belongs to order 31349 (same customer 65); even repeated attempts to publish it for 66823 must fail before final text or successful history.
T04: same-day and early confirmations. T05: unavailable source, including an unreachable SQL Server with the snapshot still present.

Live investigation answers link each invoice and stock issue to a read-only WWI detail page. Opening a page repeats the order lookup with the current customer and supplier scopes. A record outside the linked order returns 404, including an invoice from another order of the same customer. An unavailable WWI source returns an unavailable result. The stock issue detail displays the authorized prior receipts as same-item history with an explicit unknown purchase source.

For a standalone date comparison, the card shows the expected date, each linked invoice's confirmation and calendar-day offset when available, and the query or snapshot time. Any cited foreign invoice is still identified as unsupported. An attributed non-receipt report and a later confirmation can coexist when they refer to different dates. The renderer gives this explanation only for a recognized complaint statement about the expected day and a later non-credit invoice on that order.
