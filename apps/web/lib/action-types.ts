export type ActionState =
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "EXECUTING"
  | "UNKNOWN"
  | "RECONCILING"
  | "SUCCEEDED"
  | "REJECTED"
  | "EXPIRED"
  | "REVOKED"
  | "CONFLICT"
  | "MANUAL_REVIEW"
  | "CANCELLED"
  | "COMPENSATED";

export type ActionRecord = {
  action_id: string;
  action_type: string;
  current_revision: number;
  payload_hash: string;
  state: ActionState;
  expires_at: string;
  remote_ref?: string | null;
  compensates_action_id?: string | null;
  payload_json: {
    target: {
      system: string;
      company: string;
      customer_id: string;
      order_id: string;
    };
    parameters: {
      title: string;
      body: string;
      assignee_id: string;
      due_at: string;
    };
    preconditions: { target_version: string };
    side_effects: string[];
  };
};

export type ActionEvent = {
  event_id: number;
  event_type: string;
  actor_id: string;
  details_json: Record<string, unknown>;
  event_hash: string;
  created_at: string;
};
