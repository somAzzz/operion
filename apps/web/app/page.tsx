"use client";

import {
  defineToolkit,
  useAui,
  useAuiState,
  AuiProvider,
  AuiConfig,
  Suggestions,
  ThreadListItemPrimitive,
  ThreadListPrimitive,
  Tools,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import {
  ArchiveIcon,
  Clock3Icon,
  DatabaseIcon,
  HistoryIcon,
  MessageSquareTextIcon,
  PackageCheckIcon,
  SendIcon,
  PlusIcon,
  ShieldCheckIcon,
  Trash2Icon,
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

function FollowupProposalCard({ result }: ToolRenderProps) {
  const data = result?.data ?? {};
  const target = (data.target ?? {}) as Record<string, unknown>;
  const parameters = (data.parameters ?? {}) as Record<string, unknown>;
  if (!result) return <div className="result-card is-loading">Saving a reviewable proposal…</div>;
  if (!result.ok) {
    return <div className="result-card is-error"><strong>Proposal was not created</strong><span>{String(result.error?.message ?? "Rejected by the action service")}</span></div>;
  }
  return (
    <section className="result-card proposal-result" aria-label="Follow-up task proposal">
      <div className="result-card__eyebrow"><SendIcon aria-hidden="true" />Pending human approval</div>
      <h3>{String(parameters.title ?? "Internal follow-up")}</h3>
      <p>{String(target.order_id ?? "")}</p>
      <code>{String(data.action_id ?? "")}</code>
      <Link className="proposal-link" href="/approvals">Review exact revision</Link>
      <small>No Twenty Task exists until a different authorized user approves it.</small>
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
  propose_followup_task: {
    description: "Save one internal follow-up proposal for separate human approval.",
    parameters: {
      type: "object",
      properties: {
        case_id: { type: "string" },
        title: { type: "string" },
        body: { type: "string" },
        due_at: { type: "string", description: "ISO-8601 time with timezone" },
      },
      required: ["case_id", "title", "body", "due_at"],
    },
    render: (props) => <FollowupProposalCard {...(props as ToolRenderProps)} />,
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

function ConversationHistoryItem() {
  return (
    <ThreadListItemPrimitive.Root className="conversation-history__item">
      <ThreadListItemPrimitive.Trigger className="conversation-history__trigger">
        <MessageSquareTextIcon aria-hidden="true" />
        <span>
          <ThreadListItemPrimitive.Title fallback="New conversation" />
        </span>
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Delete
        className="conversation-history__delete"
        aria-label="Delete conversation"
        title="Delete conversation"
        onClick={(event) => {
          if (!window.confirm("Delete this conversation and its saved messages?")) {
            event.preventDefault();
          }
        }}
      >
        <Trash2Icon aria-hidden="true" />
      </ThreadListItemPrimitive.Delete>
    </ThreadListItemPrimitive.Root>
  );
}

function ConversationHistory() {
  const isLoading = useAuiState((state) => state.threads.isLoading);
  const threadCount = useAuiState((state) => state.threads.threadIds.length);
  return (
    <section className="conversation-history" aria-label="Conversation history">
      <div className="conversation-history__header">
        <span><HistoryIcon aria-hidden="true" />History</span>
        <ThreadListPrimitive.New aria-label="Start a new conversation">
          <PlusIcon aria-hidden="true" />
        </ThreadListPrimitive.New>
      </div>
      <ThreadListPrimitive.Root className="conversation-history__list">
        <ThreadListPrimitive.Items
          components={{ ThreadListItem: ConversationHistoryItem }}
        />
      </ThreadListPrimitive.Root>
      {isLoading ? (
        <p className="conversation-history__empty">Loading history…</p>
      ) : null}
      {!isLoading && threadCount === 0 ? (
        <p className="conversation-history__empty">No saved conversations yet.</p>
      ) : null}
    </section>
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
      {
        title: "Propose follow-up",
        label: "review the F03 shortfall",
        prompt: "检查 F03，并为这个缺口提出一个两天后到期的内部跟进任务。",
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
          <div className="rail-status"><span className="status-dot" />Controlled actions</div>
          <dl>
            <div><dt><ShieldCheckIcon aria-hidden="true" />Access</dt><dd>Scoped</dd></div>
            <div><dt><ArchiveIcon aria-hidden="true" />Tools</dt><dd>2 reads + 1 proposal</dd></div>
            <div><dt><DatabaseIcon aria-hidden="true" />Sources</dt><dd>Twenty + ERPNext</dd></div>
          </dl>
          <ConversationHistory />
          <p className="rail-note">The Agent can save a proposal, but only a separate approval and deterministic worker can create one internal Task.</p>
        </aside>
        <section className="chat-workspace" aria-label="Controlled business assistant">
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
