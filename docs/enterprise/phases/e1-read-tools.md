# E1: Data and read-only business tools

Status: PASSED, experimental scope, 2026-09-19. Owners: developer and system/data owner; business owner defines fulfillment semantics. Historical acceptance does not limit the current interface to two tools.

## Historical acceptance

The identity map marked orders/lines with no remaining quantity and no target import as `not_applicable`. GET-only readback matched ERPNext 72/72 and Twenty 35/35, with zero missing/extra source keys. Customer overview, frozen fulfillment, and the original two-entry MCP passed all fifteen C01–C03/F01–F06/P01–P03/A01–A03 cases.

ERPNext gates cover protected business DocTypes rather than claiming the entire token is globally read-only: Customer, Supplier, Item, Sales Order, Purchase Order, Warehouse, Bin, UOM were readable and denied create/update/delete/submit/cancel/amend; direct create probes returned 403. Contact and ToDo were explicit business-approved exceptions. MCP accepts no token/role/scope/URL argument; server configuration owns caller scope.

Local ignored package: `reports/enterprise/e1/20260919T-e1-complete/`. See the [read contract](../../../contracts/e1-read-tools-v1.md).

## Later interview contract revision (2026-09-22)

Original P02/v1 excluded email/phone. That is historical acceptance, not the current field interface. [Contact overviews v2](../../../contracts/contact-overviews-v2.md) returns source-verified communication fields for authorized organizations: snapshots only for `public_sample`/`simulated` data, live customer fields from Twenty Person and supplier fields from ERPNext Contact with relation checks. Credit limits, payment terms, and arbitrary notes remain excluded. Real-data field authorization needs E5.1.

Current MCP exposes fifteen snapshot or fourteen live domain reads. Agent and MCP share domain rules. The [current queue](../improvement-plan.md) owns later live/task acceptance.

## Goal and entry

E0 permission baseline plus read credentials; preparation uses separate ETL/human authority. Without a model, resolve overview, calculate frozen fulfillment, and verify evidence. Reuse ETL without requiring continuous synchronization.

| ID | Subgoal/deliverable | Verification |
| --- | --- | --- |
| E1.1 | Complete linked customers, contacts, orders, purchase lines, stock fixtures | API readback agrees with map; no same-name merge; historical/simulated labels |
| E1.2 | Bounded read adapters, fields, pagination, timeout, normalized errors | Multiple pages, failure, empty, and forbidden remain distinct; no write credential dependency |
| E1.3 | Units, remaining quantity, allocation, dates, missing-value rules | F01–F06 fixed expectations; no double allocation across orders |
| E1.4 | Overview identity, contacts/owner, orders, sources/time | C01–C03; ambiguity returns candidates |
| E1.5 | Scope on search/detail/relations/aggregates/links/cache/errors | Direct P01/P02; no cross-user cache leak |
| E1.6 | MCP over business services; initially overview/fulfillment | Same rules/results as application; forged role/arbitrary address rejected |

## Minimum tool contract

Name/version, business purpose, strict input/extra-field handling, scope, result schema, row/byte/time limits, source time, missing fields, errors, effects. Test effects instead of relying only on read-only annotations. Stock calculations preserve inputs, allocations, rules, and per-line evidence. Missing reservations/dates yield insufficient information; draft documents are not effective orders/stock.

## Verification tasks

- Pin C/F inputs and independent expectations, never model-generated gold.
- Direct P01/P02 scope/field checks; P03 proves no write capability.
- A02/A03 distinguish failure, staleness, and observation gaps; A01 source notes remain data and are exercised with the model in E2.
- Test bounds, pagination/completeness, partial markers, invalid IDs, nulls, and unit semantics.
- Real isolated APIs verify target permission/readback; mocks do not replace them.

## Exit and failure

Deliver contracts, fixtures, rules, API evidence, and acceptance package. Values/identities/provenance/time/scope must agree. E1 does not prove Agent behavior. Keep insufficient information when facts/rules are missing; repair inputs and retest, never estimate with the model or silently rewrite mappings. Continue to [E2](e2-read-agent.md).
