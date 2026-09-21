# Interview demo script

Dataset: `interview-demo-v1`; seed 42; business date 2026-09-15; all records are
simulated and use the `DEMO` prefix. Snapshot answers must display the configured
observation time and must not be described as live.

Natural-language questions with checkable answers:

1. “列出我有权限查看的客户。” — 10 customers; first page is sorted by name.
2. “查找名称包含 Northstar 的客户。” — two candidates:
   `DEMO Northstar Packaging GmbH` (`...:customer:001`) and
   `DEMO Northstar Packaging Nord GmbH` (`...:customer:002`); do not auto-select.
3. “查看 DEMO Summit Sample GmbH 的概览。” — customer 010 exists and has zero
   sales orders; this is not a source error.
4. “查看 DEMO Northstar Packaging GmbH 最近的订单。” — customer 001 has nine
   sales orders, satisfying the eight-order edge case.
5. “打开销售订单 DEMO-SO-001。” — canonical order
   `operion:demo:interview-v1:sales-order:001`, dated 2026-08-08, confirmed
   `to_deliver`, EUR 3.90 tax-exclusive, one line: 2 Units at EUR 1.95.
6. “列出 2026-09-01 到 2026-09-30 的销售订单。” — apply inclusive date bounds
   and show native docstatus and business status separately.
7. “只列出已确认待交付销售订单。” — filter `confirmed_open`; drafts must not
   appear.
8. “列出供应商。” — five authorized suppliers when the complete demo supplier
   scope is configured.
9. “查看 DEMO Elm Protective Goods GmbH。” — supplier 005 exists and has zero
   purchase orders.
10. “打开采购订单 DEMO-PO-001。” — canonical order
    `operion:demo:interview-v1:purchase-order:001`, dated 2026-08-17, confirmed
    `to_receive`, EUR 280.93 tax-exclusive, four lines.
11. “列出所有已确认待收货采购订单。” — filter `confirmed_open`; native drafts
    are excluded.
12. “给我下一页销售订单。” — use the returned opaque `next_cursor`; across five
    pages of seven, all 30 IDs appear exactly once.

Stable IDs should be passed from list/search results into detail calls. Do not use
display names to guess relationships and do not claim any purchase order is
dedicated replenishment for a sales order.
