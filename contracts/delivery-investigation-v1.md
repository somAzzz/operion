# WWI order delivery investigation

Ask the interview Agent: **“Order 66823: our warehouse says nothing arrived on the 18th. Was it late, and did all 48 units arrive?”** The final investigation card in chat quotes the request as unverified, compares dates, lists picking evidence, identifies what remains unknown and suggests checking the itemized receipt. The investigation does not change a business record.

Agent function calling and the independent stdio MCP server expose the same read-only capability, `get_order_delivery_evidence(order_id)`, only for the WWI interview snapshot. It resolves a scoped sales order before reading invoice data. The MCP result is structured evidence; the Agent presents it through its existing verified Markdown answer path.

**Source and scope.** [The versioned extract](../data/canonical/interview-wwi-v1/delivery-evidence-v1.json) covers the 30 original sales orders, including explicitly empty matches, bound to the original order CSV by SHA-256. Every invoice must match the resolved order and customer. Preserve separate invoices, including credit notes. Confirmation time and the presence of a recipient come from the same source JSON; recipient names are not exported. Extraction time is not delivery time. Source datetime values are compared as recorded calendar dates, without inventing a time zone.

**Results.** A complete empty result means no linked invoice in this slice. An ordinary invoice can have or lack confirmation; a credit note cannot produce a delivery-date finding. An inaccessible order does not disclose whether it exists. Source failure, invalid relationships, missing coverage, or incomplete rows produce an error, never a negative finding. A recorded confirmation does not prove physical arrival time, line-level receipt, or fault.

**Publication.** The model selects a whole investigation card. It cannot edit its cells or publish only its favorable half. The case is about one order per turn: use an explicit reference such as “order 66823” or “订单 66823”. Invoice references from a different order are invalid even for authorized records retrieved in the same run. The current request must explicitly name one order; a model lookup or prior turn cannot set the target. If it is missing or ambiguous, restate the order number. Automatically rendered error statuses must belong to the same investigation. Model routing remains subject to evaluation; these checks apply when the investigation capability is used.

**Replay from the repository root:**

```bash
# Regenerate only when refreshing the pinned public source (requires restored WWI).
PYTHONPATH=src .venv/bin/python scripts/extract_delivery_evidence.py
# Offline cases; T04 uses synthetic timestamps, T05 removes a temporary copy.
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_delivery_investigation.py -v
# Public sample, local SGLang, temporary conversation store, real AG-UI endpoint.
PYTHONPATH=src .venv/bin/python scripts/accept_delivery_investigation.py
```

T01: order 66823 / invoice 64067, confirmation one day after expected, line receipt unknown.
T02: order 73279, no linked invoice. T03: invoice 33513 belongs to order 31349 (same customer 65); even repeated attempts to publish it for 66823 must fail before final text or successful history.
T04: same-day and early confirmations. T05: unavailable snapshot.
