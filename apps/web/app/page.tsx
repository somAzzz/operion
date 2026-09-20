"use client";

import {
  defineToolkit,
  useAui,
  AuiProvider,
  AuiConfig,
  Suggestions,
  Tools,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import {
  ArchiveIcon,
  Clock3Icon,
  DatabaseIcon,
  PackageCheckIcon,
  PlusIcon,
  ShieldCheckIcon,
  UserRoundSearchIcon,
} from "lucide-react";
import Link from "next/link";

type ToolRenderProps = {
  args: Record<string, unknown>;
  result?: { ok?: boolean; data?: Record<string, unknown>; error?: Record<string, unknown> };
};

function EvidenceRows({ data }: { data: Record<string, unknown> }) {
  const sources = Array.isArray(data.sources) ? data.sources.map(String) : [];
  const observedAt = typeof data.observed_at === "string" ? data.observed_at : "—";
  return (
    <div className="evidence-meta">
      <span><DatabaseIcon aria-hidden="true" />{sources.length} sources</span>
      <span><Clock3Icon aria-hidden="true" />{observedAt}</span>
    </div>
  );
}

function CustomerOverviewCard({ args, result }: ToolRenderProps) {
  const data = result?.data ?? {};
  const customer = (data.customer ?? {}) as Record<string, unknown>;
  const orders = Array.isArray(data.orders) ? data.orders : [];
  if (!result) return <div className="result-card is-loading">Loading customer evidence…</div>;
  if (!result.ok) {
    return <div className="result-card is-error"><strong>Customer lookup needs attention</strong><span>{String(result.error?.message ?? "No result")}</span></div>;
  }
  return (
    <section className="result-card" aria-label="Customer overview evidence">
      <div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />Customer overview</div>
      <h3>{String(customer.name ?? args.customer ?? "Customer")}</h3>
      <div className="metric-row"><strong>{orders.length}</strong><span>recent orders in scope</span></div>
      <code>{String(customer.canonical_id ?? "")}</code>
      <EvidenceRows data={data} />
    </section>
  );
}

function FulfillmentResultCard({ args, result }: ToolRenderProps) {
  const data = result?.data ?? {};
  const status = String(data.result ?? "pending");
  const missing = Array.isArray(data.missing) ? data.missing.map(String) : [];
  if (!result) return <div className="result-card is-loading">Checking fulfillment evidence…</div>;
  if (!result.ok) {
    return <div className="result-card is-error"><strong>Fulfillment check unavailable</strong><span>{String(result.error?.message ?? "No result")}</span></div>;
  }
  return (
    <section className={`result-card result-${status}`} aria-label="Fulfillment result evidence">
      <div className="result-card__eyebrow"><PackageCheckIcon aria-hidden="true" />Fulfillment rule check</div>
      <h3>{String(data.case_id ?? args.case_id ?? "Case")} · {status.replaceAll("_", " ")}</h3>
      <p>{missing.length ? `Missing: ${missing.join(", ")}` : "Required evidence is present."}</p>
      <EvidenceRows data={data} />
      <small>Deterministic rule result — not a delivery guarantee.</small>
    </section>
  );
}

const toolkit = defineToolkit({
  get_customer_overview: {
    description: "Read an authorized customer, contacts, and recent orders.",
    parameters: {
      type: "object",
      properties: {
        customer: {
          type: "string",
          description: "Canonical customer ID or exact customer name.",
        },
        max_orders: { type: "integer", minimum: 1, maximum: 50 },
      },
      required: ["customer"],
    },
    render: (props) => <CustomerOverviewCard {...(props as ToolRenderProps)} />,
  },
  check_fulfillment: {
    description: "Evaluate a frozen fulfillment case with deterministic rules.",
    parameters: {
      type: "object",
      properties: { case_id: { type: "string" } },
      required: ["case_id"],
    },
    render: (props) => <FulfillmentResultCard {...(props as ToolRenderProps)} />,
  },
});

function NewThreadButton() {
  const aui = useAui();

  return (
    <button
      type="button"
      onClick={() => aui.threads.switchToNewThread()}
      className="bg-background hover:bg-accent absolute top-4 right-4 z-10 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm transition-colors"
    >
      <PlusIcon className="size-4" />
      New inquiry
    </button>
  );
}

function ThreadWithSuggestions() {
  const aui = useAui();
  const config = AuiConfig({
    suggestions: Suggestions([
      {
        title: "Customer overview",
        label: "review orders and source IDs",
        prompt: "概览客户 operion:e2:organization:customer:ambiguous-a。",
      },
      {
        title: "Fulfillment check",
        label: "evaluate case F01",
        prompt: "检查履约场景 F01。",
      },
    ]),
  });
  return (
    <AuiProvider extends={aui} config={config}>
      <Thread />
    </AuiProvider>
  );
}

export default function Home() {
  const aui = useAui();
  const config = AuiConfig({
    tools: Tools({ toolkit }),
  });

  return (
    <AuiProvider extends={aui} config={config}>
      <main className="ops-shell">
        <aside className="evidence-rail" aria-label="Workspace status">
          <div className="brand-mark">OP</div>
          <div>
            <p className="rail-kicker">OPERION</p>
            <h1>Evidence desk</h1>
          </div>
          <div className="rail-status"><span className="status-dot" />Read-only live</div>
          <dl>
            <div><dt><ShieldCheckIcon aria-hidden="true" />Access</dt><dd>Scoped</dd></div>
            <div><dt><ArchiveIcon aria-hidden="true" />Tools</dt><dd>2 reads</dd></div>
            <div><dt><DatabaseIcon aria-hidden="true" />Sources</dt><dd>Twenty + ERPNext</dd></div>
          </dl>
          <p className="rail-note">Every business answer is paired with source IDs and an observation time. Writes are unavailable.</p>
        </aside>
        <section className="chat-workspace" aria-label="Read-only business assistant">
          <header className="workspace-header">
            <div><p>Operations / inquiry</p><h2>Ask against verified records</h2></div>
            <nav className="workspace-nav" aria-label="Workspace">
              <Link href="/approvals">Approvals</Link>
              <Link href="/actions">Actions</Link>
              <NewThreadButton />
            </nav>
          </header>
          <div className="thread-frame"><ThreadWithSuggestions /></div>
        </section>
      </main>
    </AuiProvider>
  );
}
