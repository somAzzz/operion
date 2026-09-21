"use client";

import { useState, useTransition } from "react";
import type { ActionRecord } from "@/lib/action-types";
import { CheckIcon, ShieldAlertIcon, XIcon } from "lucide-react";

const SIDE_EFFECT_LABELS: Record<string, string> = {
  twenty_internal_task: "Create an internal task in Twenty",
  twenty_company_link: "Link the task to the company",
  twenty_timeline_activity: "Add an activity to the company timeline",
};

export function ApprovalList({
  initialActions,
}: {
  initialActions: ActionRecord[];
}) {
  const [actions, setActions] = useState(initialActions);
  const [message, setMessage] = useState("");
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<"approve" | "reject" | null>(null);
  const [isPending, startTransition] = useTransition();

  function decide(action: ActionRecord, decision: "approve" | "reject") {
    const actionLabel = decision === "approve" ? "approve and queue" : "reject";
    const confirmation = `${actionLabel[0].toUpperCase()}${actionLabel.slice(1)} “${action.payload_json.parameters.title}”?`;
    if (!window.confirm(confirmation)) {
      return;
    }
    setMessage("");
    setPendingActionId(action.action_id);
    setPendingDecision(decision);
    startTransition(async () => {
      try {
        const response = await fetch(
          `/api/actions/${action.action_id}/decisions`,
          {
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
          },
        );
        if (!response.ok) {
          const error = (await response.json()) as { error?: { detail?: string } };
          setMessage(error.error?.detail ?? "The decision was rejected by the server.");
          return;
        }
        setActions((current) =>
          current.filter((item) => item.action_id !== action.action_id),
        );
        setMessage(
          decision === "approve"
            ? "Follow-up approved and queued for execution."
            : "Follow-up rejected.",
        );
      } catch {
        setMessage(
          "The decision could not be sent. Check the connection and try again.",
        );
      } finally {
        setPendingActionId(null);
        setPendingDecision(null);
      }
    });
  }

  if (actions.length === 0) {
    return (
      <div className="empty-panel">
        <strong>No pending approvals</strong>
        <p>New proposals will appear here from the server-side action ledger.</p>
      </div>
    );
  }

  return (
    <div className="approval-layout">
      {message ? (
        <p className="decision-message" role="status">{message}</p>
      ) : null}
      {actions.map((action) => {
        const { target, parameters, side_effects: sideEffects } =
          action.payload_json;
        const isCurrentAction = pendingActionId === action.action_id;
        return (
          <article
            className="approval-card"
            key={action.action_id}
            aria-busy={isCurrentAction}
          >
            <div className="approval-card__topline">
              <span><ShieldAlertIcon aria-hidden="true" />Proposed follow-up</span>
              <code>rev {action.current_revision}</code>
            </div>
            <h2>{parameters.title}</h2>
            <p>{parameters.body}</p>
            <dl className="preview-grid approval-preview">
              <div><dt>Company</dt><dd>{target.company}</dd></div>
              <div><dt>Order</dt><dd>{target.order_id}</dd></div>
              <div><dt>Due</dt><dd>{new Date(parameters.due_at).toLocaleString()}</dd></div>
              <div><dt>Expires</dt><dd>{new Date(action.expires_at).toLocaleString()}</dd></div>
            </dl>
            <div className="side-effect-box">
              <strong>Approval will</strong>
              <ul>
                {sideEffects.map((effect) => (
                  <li key={effect}>
                    {SIDE_EFFECT_LABELS[effect] ?? effect.replaceAll("_", " ")}
                  </li>
                ))}
              </ul>
            </div>
            <details className="technical-details">
              <summary>Technical details</summary>
              <dl>
                <div><dt>Customer ID</dt><dd>{target.customer_id}</dd></div>
                <div><dt>Assignee ID</dt><dd>{parameters.assignee_id}</dd></div>
                <div>
                  <dt>Content digest</dt>
                  <dd><code>{action.payload_hash.slice(0, 16)}…</code></dd>
                </div>
              </dl>
            </details>
            <div className="decision-row">
              <button
                disabled={isPending}
                onClick={() => decide(action, "reject")}
                className="reject-button"
              >
                <XIcon aria-hidden="true" />
                {isCurrentAction && pendingDecision === "reject"
                  ? "Rejecting…"
                  : "Reject"}
              </button>
              <button
                disabled={isPending}
                onClick={() => decide(action, "approve")}
                className="approve-button"
              >
                <CheckIcon aria-hidden="true" />
                {isCurrentAction && pendingDecision === "approve"
                  ? "Approving…"
                  : "Approve and queue"}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
