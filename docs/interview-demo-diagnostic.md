# Interview demo diagnostic — 2026-09-21

Inspection baseline: branch `main`, commit
`47199c28a0b7aae225b867168bd992662d1f71fe`. The worktree already contained
uncommitted changes, which were preserved and extended.

## Read-only source check

The configured local read-only connections were reachable during this check:

| Source | Object | Count |
|---|---|---:|
| Twenty | Company | 15 |
| Twenty | Person | 32 |
| ERPNext | Customer | 10 |
| ERPNext | Supplier | 2 |
| ERPNext | Item | 9 |
| ERPNext | Sales Order | 15 |
| ERPNext | Purchase Order | 4 |

No external write was run. Counts describe that observation only, not the new
dataset.

The new restricted live adapter was also exercised with GET-only calls against
those sources: customer search returned 10 in-scope records on the page, supplier
search 2, sales-order list 10, and purchase-order list 4. All four results reported
`data_mode=live`; no snapshot fallback was used.

The default `operion-e2-demo-v1` canonical batch contains 12 organizations, 27
contacts, 9 products, 15 sales orders/16 lines, 10 purchase orders/35 lines, and
6 fulfillment scenarios. Each local WWI v4/E1 canonical batch contains 10
organizations, 25 contacts, 9 products, 8 sales orders/9 lines, 8 purchase
orders/33 lines, and 6 scenarios.

Checked-in local identity maps contained:

- `wwi-v1-small-20260913-v2`: 137 rows; 10 with target IDs, 127 pending.
- `wwi-v1-small-20260913-v3` and `v4`: 137 pending rows each.
- `wwi-v1-small-20260919-e1`: 107 pending and 30 not-applicable rows.
- No conflicts were recorded in those files.

The accepted enterprise reconcile artifacts cited by the E2 runbook are outside
the checked-in paths and were not reclassified from the local maps above.

## Why the product could appear to show only one customer

This was not caused by a single shortage of target data: Twenty had 15 Companies
and ERPNext had 10 Customers. It was a layered capability/scope issue:

1. The original `CanonicalRepository` only exposed exact customer overview,
   frozen fulfillment, and the newly-added scoped portfolio count. It had no
   partial search, list pagination, order detail, supplier, or purchase APIs.
2. Every call enforced `OPERION_CUSTOMER_IDS`; tests and earlier launch examples
   commonly supplied one or two IDs. That allowlist intentionally hid every
   other customer.
3. `purchase_orders.csv` and its lines existed but were not loaded into the read
   repository at all. There was no independent supplier authorization scope.
4. Customer resolution used exact display-name equality. Similar prefixes could
   not be discovered, and the UI's suggested prompt named one fixed E2 customer.
5. The web UI rendered only portfolio, exact overview, and fulfillment cards.

At inspection time, `OPERION_CANONICAL_DIR`, `OPERION_IDENTITY_MAP`,
`OPERION_CUSTOMER_IDS`, and `OPERION_SUPPLIER_IDS` were unset in both the current
process and the checked `.env`; therefore the exact scope of any separately
running service is **UNVERIFIED**. Code defaults pointed at
`data/canonical/operion-e2-demo-v1`, while startup required an explicit identity
map and customer scope. The E2 runbook example authorized two E2 customers.

The new implementation addresses tool capability, paging, separate scopes, and
UI selection. It does not replace the server-defined allowlists with a wildcard.
