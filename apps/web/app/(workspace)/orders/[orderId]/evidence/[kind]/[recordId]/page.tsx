import { notFound } from "next/navigation";
import { ActionShell } from "@/components/action-shell";
import { upstreamAuthorization } from "@/lib/upstream-auth";
import { upstreamTraceHeaders } from "@/lib/trace-headers";

export const dynamic = "force-dynamic";

type Receipt = { receipt_id: number; purchase_order_id: number; supplier: string; quantity: string; received_at: string };
type Evidence = {
  order_id: string; expected_date: string; queried_at: string;
  invoice?: { confirmed_at: string | null; credit_note: boolean };
  issue?: { invoice_id: number; stock_item_id: number; quantity: string; issued_at: string; prior_receipts: Receipt[] };
};

export default async function EvidencePage({ params }: {
  params: Promise<{ orderId: string; kind: string; recordId: string }>;
}) {
  const { orderId, kind, recordId } = await params;
  if (![orderId, recordId].every(id => /^[1-9][0-9]{0,9}$/.test(id)) || !["invoice", "issue"].includes(kind)) notFound();
  const auth = await upstreamAuthorization(process.env.OPERION_AGENT_TOKEN);
  if (!auth) notFound();
  const url = new URL(`/api/orders/${orderId}/evidence/${kind}/${recordId}`, process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000");
  const response = await fetch(url, { headers: upstreamTraceHeaders({ Authorization: auth }), cache: "no-store" }).catch(() => null);
  if (response && [401, 403, 404].includes(response.status)) notFound();
  if (!response?.ok) return <ActionShell eyebrow="WWI" title="Delivery evidence unavailable"><p role="status">The delivery record could not be queried. Try again later.</p></ActionShell>;
  const { order_id, expected_date, invoice, issue, queried_at }: Evidence = await response.json();
  const label = issue ? "Stock issue" : invoice?.credit_note ? "Credit note" : "Invoice";
  return <ActionShell eyebrow={issue ? "WWI · Warehouse.StockItemTransactions" : "WWI · Sales.Invoices"} title={`${label} ${recordId}`}>
    <dl className="preview-grid">
      <div><dt>Sales order</dt><dd>{order_id}</dd></div>
      {invoice && <>
        <div><dt>Expected delivery date</dt><dd>{expected_date}</dd></div>
        <div><dt>Recorded delivery confirmation</dt><dd>{invoice.confirmed_at ?? "No confirmation recorded"}</dd></div>
      </>}
      {issue && <>
        <div><dt>Linked invoice</dt><dd><a href={`/orders/${order_id}/evidence/invoice/${issue.invoice_id}`}>{issue.invoice_id}</a></dd></div>
        <div><dt>Stock item</dt><dd>{issue.stock_item_id}</dd></div>
        <div><dt>Units posted out</dt><dd>{Math.abs(Number(issue.quantity))}</dd></div>
        <div><dt>Warehouse posting time</dt><dd>{issue.issued_at}</dd></div>
      </>}
      <div><dt>WWI query time (UTC)</dt><dd>{queried_at}</dd></div>
    </dl>
    {invoice && <p>Verifying the quantity the customer received requires an itemized receipt.</p>}
    {issue && <section><h2>Prior receipts for item {issue.stock_item_id}</h2>
      <p>WWI provides no lot allocation linking this issue to a receipt. The purchase source of these {Math.abs(Number(issue.quantity))} units is unverified.</p>
      {issue.prior_receipts.length ? <ul>{issue.prior_receipts.map(r =>
        <li key={r.receipt_id}>PO {r.purchase_order_id} · Receipt {r.receipt_id} · {r.supplier} · {r.quantity} units received at {r.received_at}</li>
      )}</ul> : <p>No prior receipts returned within your supplier scope.</p>}
    </section>}
  </ActionShell>;
}
