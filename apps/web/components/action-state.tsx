import type { ActionState } from "@/lib/action-types";

const labels: Record<ActionState, string> = {
  PENDING_APPROVAL: "Pending approval",
  APPROVED: "Approved",
  EXECUTING: "Executing",
  UNKNOWN: "Result unknown",
  RECONCILING: "Reconciling",
  SUCCEEDED: "Succeeded",
  REJECTED: "Rejected",
  EXPIRED: "Expired",
  REVOKED: "Revoked",
  CONFLICT: "Conflict",
  MANUAL_REVIEW: "Manual review",
  CANCELLED: "Cancelled",
  COMPENSATED: "Compensated",
};

export function ActionStateBadge({ state }: { state: ActionState }) {
  return <span className="action-state" data-state={state}>{labels[state]}</span>;
}

export function StateGuidance({ state }: { state: ActionState }) {
  if (state === "UNKNOWN" || state === "RECONCILING") {
    return <p className="state-guidance is-warning">Do not submit another action. The worker is reconciling the original action ID.</p>;
  }
  if (state === "MANUAL_REVIEW") {
    return <p className="state-guidance is-warning">Automatic execution is frozen. An operator must compare downstream evidence.</p>;
  }
  if (state === "CONFLICT") {
    return <p className="state-guidance">A current precondition changed. Create a new preview before proceeding.</p>;
  }
  return null;
}
