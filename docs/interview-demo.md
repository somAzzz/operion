# Interview demo script

Dataset: `interview-demo-v1`; seed 42; business date 2026-09-15; all records are
simulated and use the `DEMO` prefix. Snapshot answers must display the configured
observation time and must not be described as live.

Natural-language questions with checkable answers:

1. “List the customers I am authorized to view.” — 10 customers; first page is sorted by name.
2. “Find customers whose names contain Northstar.” — two candidates:
   `DEMO Northstar Packaging GmbH` (`...:customer:001`) and
   `DEMO Northstar Packaging Nord GmbH` (`...:customer:002`); do not auto-select.
3. “Show the overview for DEMO Summit Sample GmbH.” — customer 010 exists and has zero
   sales orders; this is not a source error.
4. “Show recent orders for DEMO Northstar Packaging GmbH.” — customer 001 has nine
   sales orders, satisfying the eight-order edge case.
5. “Open sales order DEMO-SO-001.” — canonical order
   `operion:demo:interview-v1:sales-order:001`, dated 2026-08-08, confirmed
   `to_deliver`, EUR 3.90 tax-exclusive, one line: 2 Units at EUR 1.95.
6. “List sales orders from 2026-09-01 through 2026-09-30.” — apply inclusive date bounds
   and show native docstatus and business status separately.
7. “List only confirmed open sales orders.” — filter `confirmed_open`; drafts must not
   appear.
8. “List suppliers.” — five authorized suppliers when the complete demo supplier
   scope is configured.
9. “Show DEMO Elm Protective Goods GmbH.” — supplier 005 exists and has zero
   purchase orders.
10. “Open purchase order DEMO-PO-001.” — canonical order
    `operion:demo:interview-v1:purchase-order:001`, dated 2026-08-17, confirmed
    `to_receive`, EUR 280.93 tax-exclusive, four lines.
11. “List all confirmed open purchase orders.” — filter `confirmed_open`; native drafts
    are excluded.
12. “Show the next sales-order page.” — use the returned opaque `next_cursor`; across five
    pages of seven, all 30 IDs appear exactly once.

Stable IDs should be passed from list/search results into detail calls. Do not use
display names to guess relationships and do not claim any purchase order is
dedicated replenishment for a sales order.
