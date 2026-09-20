import { notFound } from "next/navigation";
import { ActionShell, ServiceUnavailable } from "@/components/action-shell";
import { ActionStateBadge, StateGuidance } from "@/components/action-state";
import type { ActionEvent, ActionRecord } from "@/lib/action-types";
import { readActionData } from "@/lib/action-server";

export default async function ActionDetailPage({ params }: { params: Promise<{ actionId: string }> }) {
  const { actionId } = await params;
  const [actionResult, eventResult] = await Promise.all([
    readActionData<ActionRecord>(`/actions/${encodeURIComponent(actionId)}`),
    readActionData<{ events: ActionEvent[] }>(`/actions/${encodeURIComponent(actionId)}/events`),
  ]);
  if (actionResult.status === 404) notFound();
  if (!actionResult.data || !eventResult.data) {
    return <ActionShell eyebrow="Control plane / action" title="Action detail"><ServiceUnavailable /></ActionShell>;
  }
  const action = actionResult.data;
  const remoteUrl = action.state === "SUCCEEDED" && action.remote_ref && action.payload_json.target.system === "twenty"
    ? `${(process.env.OPERION_TWENTY_WEB_URL ?? "http://localhost:3000").replace(/\/$/, "")}/objects/tasks/${encodeURIComponent(action.remote_ref)}`
    : null;
  return (
    <ActionShell eyebrow="Control plane / action" title={action.payload_json.parameters.title}>
      <section className="action-detail">
        <div className="action-detail__summary"><ActionStateBadge state={action.state} /><code>{action.action_id}</code><span>revision {action.current_revision}</span></div>
        <StateGuidance state={action.state} />
        <dl className="preview-grid">
          <div><dt>Target</dt><dd>{action.payload_json.target.customer_id}</dd></div>
          <div><dt>Order</dt><dd>{action.payload_json.target.order_id}</dd></div>
          <div><dt>Assignee</dt><dd>{action.payload_json.parameters.assignee_id}</dd></div>
          <div><dt>Due</dt><dd>{new Date(action.payload_json.parameters.due_at).toLocaleString()}</dd></div>
          <div><dt>Remote reference</dt><dd>{remoteUrl ? <a className="remote-link" href={remoteUrl}>{action.remote_ref}</a> : action.remote_ref ?? "Not confirmed"}</dd></div>
          <div><dt>Payload digest</dt><dd><code>{action.payload_hash.slice(0, 20)}…</code></dd></div>
        </dl>
        <h2 className="timeline-title">Immutable event timeline</h2>
        <ol className="event-timeline">
          {eventResult.data.events.map((event) => (
            <li key={event.event_id}><span /><div><strong>{event.event_type.replaceAll("_", " ")}</strong><p>{new Date(event.created_at).toLocaleString()} · {event.actor_id}</p><code>{event.event_hash.slice(0, 16)}…</code></div></li>
          ))}
        </ol>
      </section>
    </ActionShell>
  );
}
