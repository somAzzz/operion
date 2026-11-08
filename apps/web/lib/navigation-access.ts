export type NavigationAccess = Readonly<{
  evidence: boolean;
  actions: boolean;
  approvals: boolean;
}>;

/** Match existing page admission; these flags never grant backend permission. */
export function navigationAccess(roles: unknown): NavigationAccess {
  const granted = Array.isArray(roles)
    ? new Set(roles.filter((role): role is string => typeof role === "string"))
    : new Set<string>();
  const actionRead = ["action_reader", "action_approver", "action_operator"].some(
    (role) => granted.has(role),
  );
  return {
    evidence: granted.has("agent_read"),
    actions: actionRead,
    // The existing backend permits all three action roles to view the queue.
    // Sending a decision still requires action_approver at the backend.
    approvals: actionRead,
  };
}
