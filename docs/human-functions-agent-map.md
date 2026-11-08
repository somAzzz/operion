# Human workflows and Agent responsibilities

Purpose: understand the business work people perform when designing the Agent. This is not a requirement to train in every menu or complete full product training. The table lists possible assistance, not a claim that each capability is currently implemented or authorized.

| Function | Human workflow | Possible Agent assistance | Judgment retained by people | Important exceptions |
| --- | --- | --- | --- | --- |
| Customers/contacts | Create, deduplicate, link, maintain | Search, candidate comparison, organize, preview | Identity and trusted sources | Duplicate names, shared email, multiple legal entities, missing fields |
| Opportunities/follow-up | Record need, stage, owner, next step | Summarize history, reminders, Task draft | Priority, likelihood, communication | Stale opportunity, missing owner, historical order mistaken for opportunity |
| CRM-to-ERP handoff | Establish trading customer | Validate required fields, preview, ID linking | Account opening, terms, credit | Existing ERP party, changed name, partial creation |
| Quotations/orders | Select goods, quantities, prices, discount, dates | Query, prepare draft | Exceptions, committed dates, confirmation | UOM errors, stale price, duplicate order |
| Purchasing | Review demand, supplier, quantity, date | Shortfall analysis, suggestions, draft | Supplier, budget, purchase commitment | Duplicate inbound, uncertain lead time, MOQ |
| Receiving/delivery | Count/inspect goods, batches, receipts/issues | Pending documents, entry discrepancies | Physical arrival and quality | Partial receipt, damage, wrong batch, partial delivery |
| Invoices/payments | Reconcile trade, invoice, match payment | Open invoice/receivable/payable summaries, candidates | Tax exceptions, posting, actual payment | Duplicate invoice, fees/FX, payment mismatch |
| Inventory | Count, transfer, adjust, trace batch | Explain quantity differences, suggest count | Actual stock and adjustment approval | Reservations, multiple warehouses, negative stock, expiry |
| Returns/corrections | Find original document, cause, correction path | Trace related effects and propose steps | Return/reversal/stock-adjustment approval | Closed periods, delivered records, immutable related documents |
| Customer operations | Consolidate orders, follow-up, debt across pages | Cross-system summary, links, next-step suggestions | Customer communication and next action | Staleness, incompatible amount definitions, forbidden data |
| Data quality | Inspect import errors, mappings, duplicates | Locate/classify errors, correction preview | Meaning of missing data, merges, rule changes | Duplicate execution, orphan lines, wrong units |
| Permission management | Assign role/company/operation scope | Explain existing permission/application path | All authorization changes | Cross-company reads, sensitive-field disclosure |

## Enough business understanding

For each priority task, explain what the user wants and whether input is sufficient;
which system supplies facts; whether output is a query, recommendation, draft, or
formal action; which decisions remain human; and how empty/conflicting/forbidden/
failed results are communicated. A sample document or short walkthrough is enough
for uncertainty; full end-to-end operator training is not a prerequisite.

| Request | Tool evidence | Expected result | Initial writes |
| --- | --- | --- | --- |
| Related customer orders and follow-up owner | CRM contacts/owner, ERP orders/delivery | Facts, links, times | None |
| Fulfillment at the pinned demo date | Remaining demand, stock/reservation, inbound/date, transport/shipment rules | Satisfiable, shortfall, or insufficient information with evidence | None |
| Why an import failed | Source row, batch, rule version, validation/target error | Later error explanation and repair suggestion | None |

People confirm rule scope and missing-information handling, not learn the full
inventory algorithm. Tools calculate pinned stock/inbound allocation; the model
selects evidence. Develop business understanding and data preparation in parallel,
with acceptance cases from initial task design. Accounting summaries and complete
opportunity analysis are not minimum-demo prerequisites.

## Design principles

Start with one clear read-only task and a deterministic contract. Keep identity resolution, business calculations, state interpretation, permission, and execution in domain/server code. The model routes requests and selects evidence for server-rendered answers; it does not invent accounting facts or hold write credentials.

The original demonstration focuses on customer overview and fulfillment rules; current query capabilities also cover suppliers, contacts, orders, and aggregates. The first write remains one independently approved internal follow-up Task. Additional functions in the table need separate business scope/contracts/acceptance.

Use source-backed facts, provenance/time, explicit missing information, and distinct error meanings. Duplicate names require clarification, not automatic merging. Frozen fulfillment is not a live delivery promise.

## Useful business understanding

Understand the distinction between Twenty Company and ERPNext Company/customer, customer versus supplier, draft versus confirmed/posted state, ordered/picked/delivered quantities, warehouse stock versus allocatable stock, and tax-exclusive amounts/currency/UOM.

Learn the normal business path and a small set of exceptions relevant to the chosen task. Use read-only queries and a few supported isolated operations rather than preparing every business document type.

## What remains human-controlled

Formal orders, posting, payment, inventory changes, customer identity/credit decisions, external communications, and permissions remain human business-system responsibilities unless a new controlled capability is separately released. Approval refers to exact persisted content; the server rechecks authority and state, executes idempotently, and verifies by readback.

See [Agent / MCP boundaries](agent-boundaries.md), the [minimum demo](minimum-demo.md), and the [current implementation queue](enterprise/improvement-plan.md).
