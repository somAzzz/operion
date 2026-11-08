# E4: One controlled write — internal follow-up Task

Historical status: PASSED, isolated public/simulated data, 2026-09-20. Developer and Twenty owner implement; business owner confirms effects. No real-data release follows from this pass.

## Goal and subgoals

Entry: E0–E3 passed. Complete one Task loop in a running isolated Twenty instance, without customer updates, external messages, or order writes.

| ID | Deliverable | Acceptance |
| --- | --- | --- |
| E4.1 | Fixed customer/order/title/body/owner/deadline/timezone/effects/unique-reference contract | Installed-version fields; no arbitrary model object/field selection |
| E4.2 | `propose_followup_task` records a normalized proposal | Target Task count unchanged before approval; proposal traceable |
| E4.3 | Proposal card → independent `/approvals`; `/actions` events | Exact target/content/revision/time/effects; rejection creates no Task; chat closure does not lose action |
| E4.4 | Limited Worker API adapter with Task credential/readback | One exact Task/association; mismatch requires review |
| E4.5 | Applicable W01–W15 API/UI integration | No duplicates on response loss, restart, concurrency, pause |
| E4.6 | Shortfall → suggestion → approval → creation → links/events → compensation | Visible pending/executing/unknown/success; operator can reconcile |

## Target probe release rules

Any unique-reference field/extension is an administrator maintenance change with compatibility/upgrade ownership, never an Agent capability. Record unavoidable excess credential rights and seek target restrictions; broad authority plus a prompt is not least privilege. Worker paths/fields remain fixed with no model URL/GraphQL.

Actually create isolated Tasks to check notifications, assignment, and workflows. External-contact sending exceeds scope: disable the effect or block release; renaming the tool “internal” does not fix it.

## Business cases

- Correct shortfall customer/order produces one internal Task.
- Unresolved duplicate names cannot produce executable targets; invalid/out-of-scope owner fails.
- Duplicate approval, HTTP retry, and restored model conversation do not duplicate the effect.
- A deliberate second identical Task has a new action ID; duplicate-candidate prompting remains a UI design requirement, not an asserted current implementation.
- No business-system write before approval. Unknown outcome is not presented as failure with encouragement to recreate.
- Read back body, relationships, owner, deadline, state; audit links request and approval.
- Client payload replacement, repeated clicks, old revision, and cross-user replay are rejected/idempotent.
- Cards/action pages preserve `UNKNOWN/RECONCILING` without a recreate shortcut.

## Exit

Deliver Task contract, real-API fault evidence, UI flow under the [frontend plan](../frontend-plan.md), exact action lookup, and recovery instructions. Original fifteen plus W01–W15 provide at least thirty case IDs; state inapplicability by version, and record model variants separately. M2 is isolated public/simulated demonstration, not enterprise write approval; remain isolated before [E5](e5-enterprise-pilot.md).

## Historical implementation and acceptance (2026-09-20)

- Only `propose_followup_task` was added; server-rechecked shortfall yields `PENDING_APPROVAL`. Server fixes customer, ERPNext order, owner, effects, precondition, expiry.
- Different proposer/approver; Worker rechecks current Company, Workspace Member, and ERPNext order versions.
- Task ID equals action ID; deterministic UUIDv5 TaskTarget; no upsert-induced timeline replay.
- Twenty 2.39.0: zero Tasks before approval; lost response recovered from UNKNOWN; two Workers had one claim; post-commit crash recovered through lease/reconciliation; exact unique Task/Target readback.
- One-member workspace had no Notification object/table; one `recordCreated` timeline/Task and no outbound message. Reprobe after membership/email/workflow/notification changes.
- W01–W15, Python 89/89, Ruff, and production Web build passed. Probe/test Tasks were marked `DONE` normally; successful demo Tasks remained `TODO` evidence.

See [E4 contract](../../../contracts/e4-followup-task-v1.md) and [runbook](../../../ops/e4-followup-task.md). Local package: `reports/enterprise/e4/20260920T-followup-task/`. Next operational gate is E5; enterprise-data writes remain unapproved.

## Failure

Pause the tool on duplicate creation, wrong target, or unknown external notification. Reconcile affected Tasks and close/cancel through supported workflows with compensation links. Never delete database records to hide evidence.
