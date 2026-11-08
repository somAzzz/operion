# Workspace navigation access

Implemented 2026-10-17. Navigation uses server-verified current roles. Unavailable links are not rendered, avoiding Next.js RSC prefetch of forbidden pages.

| Role | Evidence desk | Actions | Approvals |
| --- | --- | --- | --- |
| `agent_read` | Visible | Hidden | Hidden |
| `followup_proposer` | Hidden | Hidden | Hidden |
| `action_reader` | Hidden | Visible | Visible |
| `action_approver` | Hidden | Visible | Visible |
| `action_operator` | Hidden | Visible | Visible |

Multiple roles form a union. All three action roles may view actions/approval queues; decisions still require backend `action_approver`, and execution operations keep their own checks. Username `admin` grants no role.

The server layout calls `/api/identity` with the trusted forwarded token. Only three navigation booleans reach the client, not the token. Identity fetch is `no-store`; React `cache` reuses only within one server render. Failure hides entries by default. An open page needs refresh for new navigation state; backends still check current authority on every request.

Home, action-shell navigation, and follow-up cards share entry components. Actions/Approvals/detail links set `prefetch={false}`. Hiding is not authorization; Next.js page/API guards and Python checks remain independent.

## Recorded validation (2026-10-17)

- `npm run test:navigation`: 6 passed for role unions, invalid roles, revoked permission, and user isolation.
- `npm run test:navigation:render`: 8 passed against production Next.js for server rendering, roles, identity failure, user switching, and direct page/RSC 403 for read-only users. Identity fixtures were isolated and synthetic; actual policy was not changed.
- TypeScript, production build, and existing six session tests passed. Checks were added to CI, local Web verification, and image builds.
- After updating local Web, an in-app browser refresh of the read-only account showed neither Actions nor Approvals in the DOM; existing conversation remained.

These bounded checks do not replace the full I06/I07 or E5 matrix. See the [current queue](improvement-plan.md).
