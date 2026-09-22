# WWI interview dataset script

Dataset: `interview-wwi-v1`; pinned WWI v1 public sample; business date
2016-05-31; `data_class=public_sample`. Names, IDs, dates, lines, quantities,
prices, and source statuses come from WWI. USD is an explicit dataset assumption
because WWI orders do not store a currency code. Snapshot results must not be
described as live.

Checkable questions:

1. “查找名称包含 Tailspin Toys 的客户。” — five authorized matches; return
   candidates with stable IDs rather than guessing one from the shared prefix.
2. “查看 Tailspin Toys (North Cowden, TX)。” — customer
   `wwi:organization:customer:65` has ten selected sales orders.
3. “查看 Tailspin Toys (East Dailey, WV)。” — customer 60 exists but has zero
   orders in this extracted dataset and authorized scope; this says nothing about
   orders in the complete WWI database.
4. “查看 Tailspin Toys (Dracut, MA)。” — customer 88 is the second explicit
   zero-order edge case in the extracted dataset, not in complete WWI.
5. “列出销售订单并翻页。” — all 30 order IDs appear exactly once when callers
   reuse each opaque `next_cursor`.
6. “打开订单 66823。” — use canonical ID `wwi:sales_order:66823`; expose its
   source status and tax-exclusive USD-assumed total without inventing ERPNext
   docstatus. Line 210128 has ordered 48, picked 48, unpicked 0, and unknown
   delivered quantity because WWI order lines provide no delivery evidence.
7. “列出供应商。” — five authorized suppliers.
8. “查看 Litware, Inc. 的采购订单。” — supplier 7 owns all 15 selected purchase
   orders.
9. “查看 Consolidated Messenger。” — supplier 3 exists and has zero selected
   purchase orders.
10. “打开采购订单 2074。” — use canonical ID `wwi:purchase_order:2074`; show
    all three source lines and the source supplier reference.

Mapping revision `interview-wwi-v1.1` corrects two material contracts without
changing the pinned WWI snapshot: `PickedQuantity` is now `picked_quantity`, not
`delivered_quantity`; purchase-order target payloads use base quantity, base UOM,
conversion factor 1, and a base-unit rate that preserves each source line amount.
For example, line 8240 is 1,592 outers × 25 units × USD 1.90 = USD 75,620.00.

The 12-product catalog is deliberately broader than the three packaging products
used by the selected complete orders. Do not infer a direct replenishment link
between a purchase order and a sales order; WWI does not provide that relation.
