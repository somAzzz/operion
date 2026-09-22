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
  unstable_useComposerInput,
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
  status: { type: string; reason?: string; error?: unknown };
};

function unresolvedToolState(
  result: ToolRenderProps["result"],
  status: ToolRenderProps["status"],
  loadingLabel: string,
) {
  if (result) return null;
  if (status.type !== "running" && status.type !== "requires-action") {
    return (
      <div className="result-card is-error" role="alert">
        <strong>Tool call did not complete</strong>
        <span>No evidence was returned. Retry the question or reduce its scope.</span>
      </div>
    );
  }
  return <div className="result-card is-loading" role="status">{loadingLabel}</div>;
}

function EvidenceRows({ data }: { data: Record<string, unknown> }) {
  const sources = Array.isArray(data.sources) ? data.sources.map(String) : [];
  const observedAt = typeof data.observed_at === "string" ? data.observed_at : "—";
  const verification = (data.cross_system_verification ?? {}) as Record<string, unknown>;
  return (
    <div className="evidence-meta">
      <span><DatabaseIcon aria-hidden="true" />{String(data.dataset_version ?? "dataset not reported")}</span>
      <span>{String(data.data_mode ?? "snapshot")} · {String(data.data_class ?? "—")}</span>
      <span>Business date {String(data.business_date ?? "—")}</span>
      <span><Clock3Icon aria-hidden="true" />Observed {observedAt}</span>
      <span>{String(data.query_scope ?? `${sources.length} sources`)}</span>
      {verification.status === "not_verified" ? <span>Live cross-system identity not verified</span> : null}
    </div>
  );
}

function SelectStableId({ id, noun }: { id: string; noun: string }) {
  const composer = unstable_useComposerInput();
  return (
    <button
      type="button"
      className="result-card__select"
      onClick={() => composer.setText(`Show me ${noun} ${id}.`)}
    >
      Use this {noun}
    </button>
  );
}

function ResultError({ result, label, noun }: { result?: ToolRenderProps["result"]; label: string; noun: "customer" | "supplier" }) {
  if (result?.ok !== false) return null;
  const candidates = Array.isArray(result.error?.candidates) ? result.error.candidates : [];
  return (
    <div className="result-card is-error">
      <strong>{label}</strong>
      <span>{String(result.error?.message ?? "Source unavailable")}</span>
      {candidates.map((candidate, index) => {
        const row = candidate as Record<string, unknown>;
        const id = String(row.canonical_id ?? "");
        return <div key={id || index}><span>{String(row.name ?? id)}</span>{id ? <SelectStableId id={id} noun={noun} /> : null}</div>;
      })}
    </div>
  );
}

function SearchResultsCard({ result, status, kind }: ToolRenderProps & { kind: "customer" | "supplier" }) {
  const data = result?.data ?? {};
  const rows = Array.isArray(data.results) ? data.results : [];
  const pagination = (data.pagination ?? {}) as Record<string, unknown>;
  const unresolved = unresolvedToolState(result, status, `Searching ${kind}s…`);
  if (!result) return unresolved;
  if (!result.ok) return <ResultError result={result} label={`${kind} search unavailable`} noun={kind} />;
  return (
    <section className="result-card" aria-label={`${kind} search results`}>
      <div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />{kind} results</div>
      <h3>{rows.length ? `${rows.length} on this page` : `No ${kind}s in the current dataset and authorized scope`}</h3>
      <div className="result-list">
        {rows.map((item) => {
          const row = item as Record<string, unknown>;
          const id = String(row.canonical_id ?? "");
          return <div className="result-list__item" key={id}><div><strong>{String(row.name ?? id)}</strong><span>{String(row.city ?? "")} · {String(row.country ?? "")}</span><code>{id}</code></div><SelectStableId id={id} noun={kind} /></div>;
        })}
      </div>
      {pagination.has_more ? <small>More results are available; use the returned cursor to continue.</small> : null}
      <EvidenceRows data={data} />
    </section>
  );
}

function ContactSearchCard({ result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const rows = Array.isArray(data.results) ? data.results : [];
  const pagination = (data.pagination ?? {}) as Record<string, unknown>;
  const unresolved = unresolvedToolState(result, status, "Searching contacts…");
  if (!result) return unresolved;
  if (!result.ok) return <div className="result-card is-error"><strong>Contact search unavailable</strong><span>{String(result.error?.message ?? "No result")}</span></div>;
  return (
    <section className="result-card" aria-label="Contact search results">
      <div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />Contact results</div>
      <h3>{rows.length ? `${rows.length} on this page` : "No matching contacts in the current dataset and authorized scope"}</h3>
      <div className="result-list">
        {rows.map((item) => {
          const row = item as Record<string, unknown>;
          const id = String(row.canonical_id ?? "");
          const organizationId = String(row.organization_id ?? "");
          const noun = row.organization_role === "supplier" ? "supplier" : "customer";
          return <div className="result-list__item" key={id}><div><strong>{String(row.full_name ?? id)}</strong><span>{String(row.organization_name ?? "")} · {String(row.organization_role ?? "")}</span><code>{id}</code></div><SelectStableId id={organizationId} noun={noun} /></div>;
        })}
      </div>
      {pagination.has_more ? <small>More results are available; use the returned cursor to continue.</small> : null}
      <EvidenceRows data={data} />
    </section>
  );
}

function ContactDetailCard({ result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const contact = (data.contact ?? {}) as Record<string, unknown>;
  const fields = (data.fields ?? {}) as Record<string, Record<string, unknown>>;
  const unresolved = unresolvedToolState(result, status, "Verifying contact details…");
  if (!result) return unresolved;
  if (!result.ok) return <div className="result-card is-error"><strong>Contact lookup needs attention</strong><span>{String(result.error?.message ?? "No result")}</span></div>;
  return <section className="result-card" aria-label="Verified contact details">
    <div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />Contact detail</div>
    <h3>{String(contact.full_name ?? "Contact")}</h3>
    <p>{String(contact.organization_name ?? "")} · {String(contact.organization_role ?? "")}</p>
    <code>{String(contact.canonical_id ?? "")}</code>
    <p>Email: {fields.email?.state === "present" ? String(fields.email.value) : String(fields.email?.state ?? "unavailable")}</p>
    <p>Phone: {fields.phone?.state === "present" ? String(fields.phone.value) : String(fields.phone?.state ?? "unavailable")}</p>
    <p>Source: {String(fields.email?.source_system ?? data.record_source_system ?? "unknown")} · mapping {String(contact.mapping_status ?? "unknown")}</p>
    <EvidenceRows data={data} />
  </section>;
}

function CustomerOrderContextCard({ result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const resolution = (data.resolution ?? {}) as Record<string, unknown>;
  const overview = (data.customer_overview ?? {}) as Record<string, unknown>;
  const orders = Array.isArray(overview.orders) ? overview.orders : [];
  const unresolved = unresolvedToolState(result, status, "Verifying customer and sales order…");
  if (!result) return unresolved;
  if (!result.ok) return <div className="result-card is-error"><strong>Customer and order do not match</strong><span>{String(result.error?.message ?? "No result")}</span></div>;
  return <section className="result-card" aria-label="Verified customer and sales order">
    <div className="result-card__eyebrow"><ArchiveIcon aria-hidden="true" />Order-backed customer resolution</div>
    <h3>{String(resolution.customer_name ?? "Customer")}</h3>
    <p>Order {String(resolution.order_id ?? "")} identifies customer {String(resolution.customer_id ?? "")}</p>
    <p>{orders.length} sales orders returned in the authorized scope</p>
    <EvidenceRows data={data} />
  </section>;
}

function OrderListCard({ result, status, kind }: ToolRenderProps & { kind: "sales order" | "purchase order" }) {
  const data = result?.data ?? {};
  const orders = Array.isArray(data.orders) ? data.orders : [];
  const pagination = (data.pagination ?? {}) as Record<string, unknown>;
  const unresolved = unresolvedToolState(result, status, `Loading ${kind}s…`);
  if (!result) return unresolved;
  if (!result.ok) return <ResultError result={result} label={`${kind} list unavailable`} noun={kind === "sales order" ? "customer" : "supplier"} />;
  return (
    <section className="result-card" aria-label={`${kind} list`}>
      <div className="result-card__eyebrow"><ArchiveIcon aria-hidden="true" />{kind}s</div>
      <h3>{orders.length ? `${orders.length} on this page` : `No matching ${kind}s in the current dataset and authorized scope`}</h3>
      <div className="result-list">
        {orders.map((item) => {
          const row = item as Record<string, unknown>;
          const id = String(row.canonical_id ?? "");
          const nativeStatus = row.native_status as Record<string, unknown> | null;
          return <div className="result-list__item" key={id}><div><strong>{String(row.order_number ?? id)}</strong><span>{String(row.customer_name ?? row.supplier_name ?? "")} · {String(row.order_date ?? "")}</span><span>{String(row.net_total_ex_tax || "amount unavailable")} {String(row.currency ?? "")} · source status: {String(row.source_status ?? "unknown")}</span>{nativeStatus ? <span>ERPNext docstatus: {String(nativeStatus.docstatus)}</span> : <span>No ERPNext native status in this snapshot</span>}<code>{id}</code></div><SelectStableId id={id} noun={kind} /></div>;
        })}
      </div>
      {pagination.has_more ? <small>Results are truncated; continue with next_cursor.</small> : null}
      <EvidenceRows data={data} />
    </section>
  );
}

function OrderDetailCard({ result, status, kind }: ToolRenderProps & { kind: "sales order" | "purchase order" }) {
  const data = result?.data ?? {};
  const order = (data.order ?? {}) as Record<string, unknown>;
  const lines = Array.isArray(data.lines) ? data.lines : [];
  const unresolved = unresolvedToolState(result, status, `Loading ${kind} details…`);
  if (!result) return unresolved;
  if (!result.ok) return <ResultError result={result} label={`${kind} unavailable`} noun={kind === "sales order" ? "customer" : "supplier"} />;
  return (
    <section className="result-card" aria-label={`${kind} detail`}>
      <div className="result-card__eyebrow"><ArchiveIcon aria-hidden="true" />{kind} detail</div>
      <h3>{String(order.order_number ?? order.canonical_id ?? kind)}</h3>
      <p>{String(order.customer_name ?? order.supplier_name ?? "")} · {String(order.order_date ?? "")} · source status: {String(order.source_status ?? "unknown")}</p>
      <div className="result-list">
        {lines.map((item) => {
          const row = item as Record<string, unknown>;
          const isSales = kind === "sales order";
          const delivered = String(row.delivered_quantity ?? "");
          return <div className="result-list__item" key={String(row.canonical_id)}><div><strong>{String(row.product_name ?? row.description ?? "Item")}</strong><span>{String(row.quantity)} {String(row.uom)} × {String(row.unit_price_ex_tax)} {String(row.currency)}</span>{isSales ? <><span>Picked: {String(row.picked_quantity || "unknown")} · unpicked: {String(row.unpicked_quantity || "unknown")}</span><span>Delivered: {delivered || "unknown — no delivery evidence in this dataset"}</span></> : <span>Base quantity: {String(row.base_quantity)} {String(row.uom)} ({String(row.ordered_outers)} outers × {String(row.units_per_outer)})</span>}<span>{String(row.net_amount)} {String(row.currency)} · expected {String(row.delivery_date ?? "—")}</span></div></div>;
        })}
      </div>
      <EvidenceRows data={data} />
    </section>
  );
}

function SupplierOverviewCard({ args, result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const supplier = (data.supplier ?? {}) as Record<string, unknown>;
  const orders = Array.isArray(data.orders) ? data.orders : [];
  const unresolved = unresolvedToolState(result, status, "Loading supplier evidence…");
  if (!result) return unresolved;
  if (!result.ok) return <ResultError result={result} label="Supplier lookup needs attention" noun="supplier" />;
  return <section className="result-card"><div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />Supplier overview</div><h3>{String(supplier.name ?? args.supplier_id ?? "Supplier")}</h3><div className="metric-row"><strong>{orders.length}</strong><span>purchase orders in the current dataset and authorized scope</span></div><code>{String(supplier.canonical_id ?? "")}</code><EvidenceRows data={data} /></section>;
}

function CustomerOverviewCard({ args, result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const customer = (data.customer ?? {}) as Record<string, unknown>;
  const orders = Array.isArray(data.orders) ? data.orders : [];
  const unresolved = unresolvedToolState(result, status, "Loading customer evidence…");
  if (!result) return unresolved;
  if (!result.ok) return <ResultError result={result} label="Customer lookup needs attention" noun="customer" />;
  return (
    <section className="result-card" aria-label="Customer overview evidence">
      <div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />Customer overview</div>
      <h3>{String(customer.name ?? args.customer ?? "Customer")}</h3>
      <div className="metric-row"><strong>{orders.length}</strong><span>orders in the current dataset and authorized scope</span></div>
      <code>{String(customer.canonical_id ?? "")}</code>
      <EvidenceRows data={data} />
    </section>
  );
}

function CustomerPortfolioCard({ result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const unresolved = unresolvedToolState(result, status, "Counting authorized customers…");
  if (!result) return unresolved;
  if (!result.ok) {
    return <div className="result-card is-error"><strong>Customer count unavailable</strong><span>{String(result.error?.message ?? "No result")}</span></div>;
  }
  return (
    <section className="result-card" aria-label="Authorized customer portfolio summary">
      <div className="result-card__eyebrow"><UserRoundSearchIcon aria-hidden="true" />Authorized customer scope</div>
      <h3>{String(data.operating_company ?? "Operating company")}</h3>
      <div className="metric-row"><strong>{String(data.customer_count ?? 0)}</strong><span>customers in the current dataset and authorized scope</span></div>
      <p>{String(data.customers_with_orders ?? 0)} with orders · {String(data.sales_order_count ?? 0)} sales orders · {String(data.open_order_count ?? 0)} open orders</p>
      <EvidenceRows data={data} />
    </section>
  );
}

function FulfillmentResultCard({ args, result, status: toolStatus }: ToolRenderProps) {
  const data = result?.data ?? {};
  const status = String(data.result ?? "pending");
  const missing = Array.isArray(data.missing) ? data.missing.map(String) : [];
  const unresolved = unresolvedToolState(result, toolStatus, "Checking fulfillment evidence…");
  if (!result) return unresolved;
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

function FollowupProposalCard({ result, status }: ToolRenderProps) {
  const data = result?.data ?? {};
  const target = (data.target ?? {}) as Record<string, unknown>;
  const parameters = (data.parameters ?? {}) as Record<string, unknown>;
  const unresolved = unresolvedToolState(result, status, "Saving a reviewable proposal…");
  if (!result) return unresolved;
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
  get_customer_portfolio_summary: {
    description: "Count and summarize customers in the authorized scope.",
    parameters: {
      type: "object",
      properties: {
        customer: {
          type: "string",
          enum: ["*"],
          description: "All customers already authorized by the server.",
        },
      },
    },
    render: (props) => <CustomerPortfolioCard {...(props as ToolRenderProps)} />,
  },
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
  search_customers: {
    description: "Search or list customers in the authorized scope.",
    parameters: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 50 }, cursor: { type: ["string", "null"] } } },
    render: (props) => <SearchResultsCard {...(props as ToolRenderProps)} kind="customer" />,
  },
  search_contacts: {
    description: "Find authorized contacts by person name and organization link.",
    parameters: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 50 }, cursor: { type: ["string", "null"] } }, required: ["query"] },
    render: (props) => <ContactSearchCard {...(props as ToolRenderProps)} />,
  },
  get_contact_by_name: {
    description: "Read one authorized contact with per-field provenance.",
    parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
    render: (props) => <ContactDetailCard {...(props as ToolRenderProps)} />,
  },
  list_sales_orders: {
    description: "List authorized sales orders by customer, date, and status.",
    parameters: { type: "object", properties: { customer_id: { type: ["string", "null"] }, date_from: { type: ["string", "null"] }, date_to: { type: ["string", "null"] }, status: { type: ["string", "null"] }, limit: { type: "integer", minimum: 1, maximum: 50 }, cursor: { type: ["string", "null"] } } },
    render: (props) => <OrderListCard {...(props as ToolRenderProps)} kind="sales order" />,
  },
  get_customer_order_context: {
    description: "Verify a sales order belongs to a named customer and return both records.",
    parameters: { type: "object", properties: { customer_query: { type: "string" }, order_id: { type: "string" }, max_orders: { type: "integer", minimum: 1, maximum: 50 } }, required: ["customer_query", "order_id"] },
    render: (props) => <CustomerOrderContextCard {...(props as ToolRenderProps)} />,
  },
  get_sales_order: {
    description: "Read one authorized sales order and its item lines.",
    parameters: { type: "object", properties: { order_id: { type: "string" } }, required: ["order_id"] },
    render: (props) => <OrderDetailCard {...(props as ToolRenderProps)} kind="sales order" />,
  },
  search_suppliers: {
    description: "Search or list suppliers in the authorized scope.",
    parameters: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 50 }, cursor: { type: ["string", "null"] } } },
    render: (props) => <SearchResultsCard {...(props as ToolRenderProps)} kind="supplier" />,
  },
  get_supplier_overview: {
    description: "Read one authorized supplier and recent purchase orders.",
    parameters: { type: "object", properties: { supplier_id: { type: "string" }, max_orders: { type: "integer", minimum: 1, maximum: 50 } }, required: ["supplier_id"] },
    render: (props) => <SupplierOverviewCard {...(props as ToolRenderProps)} />,
  },
  list_purchase_orders: {
    description: "List authorized purchase orders by supplier, date, and status.",
    parameters: { type: "object", properties: { supplier_id: { type: ["string", "null"] }, date_from: { type: ["string", "null"] }, date_to: { type: ["string", "null"] }, status: { type: ["string", "null"] }, limit: { type: "integer", minimum: 1, maximum: 50 }, cursor: { type: ["string", "null"] } } },
    render: (props) => <OrderListCard {...(props as ToolRenderProps)} kind="purchase order" />,
  },
  get_purchase_order: {
    description: "Read one authorized purchase order and its item lines.",
    parameters: { type: "object", properties: { order_id: { type: "string" } }, required: ["order_id"] },
    render: (props) => <OrderDetailCard {...(props as ToolRenderProps)} kind="purchase order" />,
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
      <PlusIcon className="size-4" aria-hidden="true" />
      New inquiry
    </button>
  );
}

function ConversationHistoryItem() {
  const title = useAuiState(
    (state) => state.threadListItem.title ?? "Untitled conversation",
  );

  return (
    <ThreadListItemPrimitive.Root className="conversation-history__item">
      <ThreadListItemPrimitive.Trigger
        className="conversation-history__trigger"
        title={title}
      >
        <MessageSquareTextIcon aria-hidden="true" />
        <span>
          <ThreadListItemPrimitive.Title fallback="New conversation" />
        </span>
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Delete
        className="conversation-history__delete"
        aria-label={`Delete conversation: ${title}`}
        title={`Delete conversation: ${title}`}
        onClick={(event) => {
          if (!window.confirm(`Delete “${title}” and its saved messages?`)) {
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
        title: "Customer count",
        label: "summarize the authorized portfolio",
        prompt: "How many customers do we have?",
      },
      {
        title: "Find customers",
        label: "search the Northstar demo accounts",
        prompt: "查找名称包含 Northstar 的客户。",
      },
      {
        title: "Purchase orders",
        label: "review confirmed orders to receive",
        prompt: "列出所有已确认待收货的采购订单。",
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
            <div><dt><ArchiveIcon aria-hidden="true" />Tools</dt><dd>10 reads + 1 proposal</dd></div>
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
