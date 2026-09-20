"use client";

import { useState, useTransition } from "react";
import type { ActionRecord } from "@/lib/action-types";
import { CheckIcon, ShieldAlertIcon, XIcon } from "lucide-react";

export function ApprovalList({ initialActions }: { initialActions: ActionRecord[] }) {
  const [actions, setActions] = useState(initialActions);
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function decide(action: ActionRecord, decision: "approve" | "reject") {
    setMessage("");
    startTransition(async () => {
      const response = await fetch(`/api/actions/${action.action_id}/decisions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Operion-Intent": "decision",
        },
        body: JSON.stringify({
          revision: action.current_revision,
          decision,
          request_id: crypto.randomUUID(),
        }),
      });
      if (!response.ok) {
        const error = (await response.json()) as { error?: { detail?: string } };
        setMessage(error.error?.detail ?? "The decision was rejected by the server.");
        return;
      }
      setActions((current) => current.filter((item) => item.action_id !== action.action_id));
      setMessage(decision === "approve" ? "Revision approved." : "Proposal rejected.");
    });
  }

  if (actions.length === 0) {
    return <div className="empty-panel"><strong>No pending approvals</strong><p>New proposals will appear here from the server-side action ledger.</p></div>;
  }

  return (
    <div className="approval-layout">
      {message ? <p className="decision-message" role="status">{message}</p> : null}
      {actions.map((action) => {
        const { target, parameters, side_effects: sideEffects } = action.payload_json;
        return (
          <article className="approval-card" key={action.action_id}>
            <div className="approval-card__topline">
              <span><ShieldAlertIcon aria-hidden="true" />Trusted server preview</span>
              <code>rev {action.current_revision}</code>
            </div>
            <h2>{parameters.title}</h2>
            <p>{parameters.body}</p>
            <dl className="preview-grid">
              <div><dt>Company</dt><dd>{target.company}</dd></div>
              <div><dt>Customer</dt><dd>{target.customer_id}</dd></div>
              <div><dt>Order</dt><dd>{target.order_id}</dd></div>
              <div><dt>Assignee</dt><dd>{parameters.assignee_id}</dd></div>
              <div><dt>Due</dt><dd>{new Date(parameters.due_at).toLocaleString()}</dd></div>
              <div><dt>Expires</dt><dd>{new Date(action.expires_at).toLocaleString()}</dd></div>
            </dl>
            <div className="side-effect-box">
              <strong>Declared side effects</strong>
              <ul>{sideEffects.map((effect) => <li key={effect}>{effect}</li>)}</ul>
            </div>
            <p className="hash-line">Content digest <code>{action.payload_hash.slice(0, 16)}…</code></p>
            <div className="decision-row">
              <button disabled={isPending} onClick={() => decide(action, "reject")} className="reject-button"><XIcon aria-hidden="true" />Reject</button>
              <button disabled={isPending} onClick={() => decide(action, "approve")} className="approve-button"><CheckIcon aria-hidden="true" />Approve exact revision</button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
