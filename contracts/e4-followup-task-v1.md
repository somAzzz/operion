# E4 internal follow-up Task contract v1

Status: Passed isolated-demo acceptance on 2026-09-20. The only real write is creation of a Twenty internal Task and its Company TaskTarget. Customer, order, stock, and ERPNext records are not modified.

## Fixed business scope

- `action_type`: `twenty.followup_task`
- `target.system`: `twenty`
- Company: server-authorized `AI Demo GmbH`
- Customer: one authorized canonical customer; the model cannot supply a Twenty Company ID
- Order: one ERPNext Sales Order resolved from a verified fulfillment case; the model cannot supply an order ID
- Owner: one fixed valid Twenty Workspace Member; the model cannot choose it
- Initial status: `TODO`
- Body: suggested internal text plus server-generated ERPNext order and fulfillment-case references
- Deadline: timezone-aware and within the next thirty days
- Approval window: thirty minutes by default

Allowed declared effects:

```text
twenty_internal_task
twenty_company_link
twenty_timeline_activity
```

The accepted isolated single-member workspace had no Notification GraphQL object/table. Acceptance observed one internal `recordCreated` timeline activity per Task and no outbound message. Adding members, email, workflows, or notification subsystems requires new probes; this observation cannot be reused automatically.

## Proposal and approval

The Agent exposes only `propose_followup_task(case_id, title, body, due_at)`. The server rereads fulfillment, permits only `shortfall`, resolves customer/order mappings, fixes owner/effects, and hashes these current preconditions with SHA-256:

- Twenty Company ID, canonical external ID, and `updatedAt`
- Workspace Member ID and active state
- ERPNext Sales Order ID, customer, `modified`, `docstatus`, and status

The tool writes only a `PENDING_APPROVAL` proposal to Operion PostgreSQL. Its fixed-length idempotency key is a SHA-256 digest of trusted conversation/run IDs, never model input. Generic Action API rejects direct client `twenty.followup_task` submissions; generic revisions cannot change E4 targets. Changed content requires a new proposal from current facts. Proposers cannot self-approve. Decisions reference `action_id + revision + decision + request_id`; execution always uses the immutable revision.

## Execution and idempotency

Only the Worker holds the Twenty write key. Recompute preconditions before sending; changed company/order/owner/permission/version becomes `CONFLICT` without a write.

Twenty Task ID equals Operion `action_id`; TaskTarget ID is UUIDv5 from the action UUID and a fixed name. Do not use `upsert=true`: isolated tests showed identical-content upsert creates another update timeline activity.

1. Read exact deterministic Task/TaskTarget IDs.
2. If present, compare title, Markdown body, dueAt, status, assignee, and Company link exactly.
3. Only absent objects use ordinary `createTask` / `createTaskTarget`.
4. Conflict, timeout, or disconnect enters `UNKNOWN`, never blind resend.
5. Reconcile by the same IDs; an existing Task with missing TaskTarget permits only deterministic Target completion.
6. Mismatched content, soft deletion, or multiple matches becomes `MANUAL_REVIEW`.

Task and TaskTarget are separate target API writes, not a cross-request atomic transaction. Deterministic IDs, exact readback, and limited completion provide recoverable partial-success semantics.

## Success by readback

Record `SUCCEEDED` only when all conditions hold:

- Unique undeleted Task ID equals action ID.
- Title, Markdown body, owner, `TODO`, and deadline match the approved revision.
- Unique TaskTarget ID points to the correct Task and approved Company.
- Worker stores remote reference and result digest in the action ledger.

Twenty normalizes timestamps to milliseconds; comparisons use that precision. Browser messages/chat history do not prove success.

## Cancellation and compensation

Cancel before sending. After sending, cancellation is only an in-flight request and reconciliation continues. E4 exposes no Agent Task update/delete. Authorized people mark erroneous/test Tasks `DONE` through Twenty's supported UI, retaining creation/update timeline. Never delete database records to hide effects. Automatic closing would need a new write contract.
