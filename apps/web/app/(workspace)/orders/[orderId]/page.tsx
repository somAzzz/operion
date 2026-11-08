import { notFound, redirect } from "next/navigation";
import { ActionShell } from "@/components/action-shell";
import { upstreamAuthorization } from "@/lib/upstream-auth";
import { upstreamTraceHeaders } from "@/lib/trace-headers";

export const dynamic = "force-dynamic";

const targets = {
  sales_order: ["ERPNext sales order", "/desk/sales-order/", "No matching ERPNext order in the visible scope."],
  company: ["Twenty customer", "/object/company/", "No linked Twenty company found."],
  person: ["Twenty order contact", "/object/person/", "Contact pending confirmation."],
  note: ["Twenty complaint", "/object/note/", "No linked complaint found."],
} as const;

type RecordKind = keyof typeof targets;
type SourceRecord = { status: string; id?: string; label?: string };

function recordUrl(kind: RecordKind, id: string) {
  const base = kind === "sales_order" ? process.env.OPERION_ERPNEXT_WEB_URL : process.env.OPERION_TWENTY_WEB_URL;
  if (!base || !URL.canParse(base)) return null;
  const url = new URL(base);
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || [".", ".."].includes(id)) return null;
  return new URL(targets[kind][1] + encodeURIComponent(id), url.origin).href;
}

export default async function OrderRecordsPage({ params, searchParams }: {
  params: Promise<{ orderId: string }>;
  searchParams: Promise<{ open?: string; record?: string; note?: string }>;
}) {
  const { orderId } = await params;
  if (!/^[1-9][0-9]{0,9}$/.test(orderId) || Number(orderId) > 2147483647) notFound();
  const { open, record: expectedId, note: complaintNote } = await searchParams;
  const openErp = open === "erpnext";
  const crmKind = open === "company" || open === "person" || open === "note" ? open : null;
  const auth = await upstreamAuthorization(process.env.OPERION_AGENT_TOKEN);
  if (crmKind === "note" || open === "sender" || (crmKind === "company" && complaintNote !== undefined)) {
    const noteId = crmKind === "note" ? expectedId : complaintNote;
    if (!noteId || !/^[0-9a-f-]{36}$/.test(noteId)) notFound();
    if (!auth || !expectedId || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(expectedId)) notFound();
    const lookup = new URL("/api/delivery-complaint", process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000");
    lookup.searchParams.set("note_id", noteId);
    const response = await fetch(lookup, {headers: upstreamTraceHeaders({Authorization: auth}), cache: "no-store"});
    if (!response.ok) {
      if ([400, 401, 403, 404].includes(response.status)) notFound();
      return <ActionShell eyebrow="Twenty CRM" title="Complaint note unavailable">Try again when Twenty is available.</ActionShell>;
    }
    const note = await response.json();
    if (note.note_id !== noteId || note.order_id !== orderId) notFound();
    if (open === "sender" && (note.sender?.status !== "verified" || note.sender.id !== expectedId)) notFound();
    if (crmKind === "company" && note.company_id !== expectedId) notFound();
    const href = recordUrl(open === "sender" ? "person" : crmKind === "company" ? "company" : "note", expectedId);
    if (!href) notFound();
    redirect(href);
  }
  const url = new URL(`/api/orders/${orderId}/records`, process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000");
  if (openErp) url.searchParams.set("erp_only", "true");
  const response = auth && await fetch(url, {
    headers: upstreamTraceHeaders({ Authorization: auth }), cache: "no-store",
  }).catch(() => null);
  if (response && response.status === 404) notFound();
  const records: Partial<Record<RecordKind, SourceRecord>> | null = response && response.ok ? await response.json() : null;
  const kind = openErp ? "sales_order" : crmKind;
  const target = kind && records?.[kind];
  if (kind && target?.status === "verified" && target.id && (openErp || target.id === expectedId)) {
    const href = recordUrl(kind, target.id);
    if (href) redirect(href);
  }
  return <ActionShell eyebrow="Source records" title={`WWI sales order ${orderId}`}>
    {crmKind && records && <p role="status">This CRM link could not be opened. Current source records are listed below.</p>}
    {records ? <dl className="preview-grid">
      {(Object.keys(targets) as RecordKind[]).map((kind) => {
        const record = records[kind];
        if (!record) return null;
        const [title, , missing] = targets[kind];
        const href = record.status === "verified" && record.id ? recordUrl(kind, record.id) : null;
        return <div key={kind}><dt>{title}</dt><dd>{href
          ? <a className="remote-link" href={href} target="_blank" rel="noopener noreferrer">{record.label ?? `Open ${title}`} ↗</a>
          : record.status === "no_match" ? missing
          : record.status === "not_configured" || record.status === "verified" ? "Source link not configured."
          : "Source relationship could not be verified."}</dd></div>;
      })}
    </dl> : <p className="empty-panel" role="status">{!auth || (response && [401, 403].includes(response.status))
      ? "Access to these order records is unavailable for this session." : "Order lookup unavailable. Try again later."}</p>}
  </ActionShell>;
}
