# E3 action-control contract v1

Status: Accepted on 2026-09-20. This historical E3 contract permits only the persistent `stub.followup_task` test adapter. It does not authorize Twenty or ERPNext writes. Later E4 scope is defined separately.

## Trust boundary

- Clients submit action reference, revision, and decision, never approver, tenant, company scope, or replacement execution parameters.
- Action Service credentials resolve identity, tenant, company, and approval authority server-side.
- Proposers cannot approve or reject their own proposals; approval and Worker identities are separate.
- Every mutation requires bearer authentication and `X-Operion-CSRF`. E3 static service credentials are for isolated acceptance only. E5 later implemented OIDC/server mappings; the actual IdP/ingress still needs environment-specific acceptance.
- Agent, browser, and Next.js client hold no downstream write credential. The E3 Worker writes only its idempotent PostgreSQL stub.

## Fixed action structure

`ProposalRequest` is strict and rejects unknown fields. Fixed values:

- `action_type`: `stub.followup_task`
- `target.system`: `e3_stub`
- `side_effects`: only `internal_stub_record`
- `target`: company, customer ID, order ID
- `parameters`: title, body, owner ID, timezone-aware deadline
- `preconditions.target_version`: target version revalidated before sending
- `expires_at`: timezone-aware approval expiry
- `idempotency_key`: unique within tenant, proposer, and action type

Same key/content returns the original `action_id`; same key/different content conflicts. Each revision stores canonical JSON, SHA-256 digest, and policy version. Parameter changes create a new revision, return to `PENDING_APPROVAL`, and invalidate old approval.

## REST contract

```text
POST /api/action-proposals
GET  /api/actions?status=PENDING_APPROVAL
GET  /api/actions/{action_id}
GET  /api/actions/{action_id}/events
POST /api/actions/{action_id}/decisions
POST /api/actions/{action_id}/revisions
POST /api/actions/{action_id}/cancel
POST /api/action-pauses
```

Decisions contain only `revision`, `decision`, `request_id`, and optional reason. `request_id` is idempotent per approver. Old revisions, expired approval, self-approval, and cross-tenant/company access fail. Out-of-scope queries appear not found to avoid disclosing existence.

## State and execution guarantees

```text
PENDING_APPROVAL -> APPROVED -> EXECUTING -> SUCCEEDED
       |              |             |
       |              |             +-> UNKNOWN -> RECONCILING
       |              |                                |-> SUCCEEDED
       |              |                                |-> APPROVED (proven not submitted)
       |              |                                +-> MANUAL_REVIEW
       |              +-> REVOKED / CONFLICT / CANCELLED
       +-> REJECTED / EXPIRED / CANCELLED
```

- Worker claims atomically with `FOR UPDATE SKIP LOCKED`, recording attempt and lease.
- Before sending, recheck company, owner, proposer permission, target version, and pause state.
- Only proven no-submission failures may return to `APPROVED`. Lost responses or crashes in the remote commit window enter `UNKNOWN/RECONCILING`.
- Lease expiry does not trigger a second write; first reconcile by stable `action_id`.
- Zero results may allow safe retry; one matching digest recovers success; multiple results or a mismatch require `MANUAL_REVIEW`.
- Compensation is a new action/approval referencing original success, never a rewrite of successful history.

## Persistence and audit

PostgreSQL stores actions, immutable revisions/decisions, attempts, pauses, append-only events, and stub effects. Each event contains the preceding digest, forming a per-action hash chain. Runtime role `operion_action_app` cannot UPDATE/DELETE revisions, decisions, or events. A separate privileged identity runs explicit migrations; API/Worker startup never migrates automatically.

The chain detects ordinary database alteration, not external tamper-proof storage. Administrator audit, independent backup, and retention are E5 responsibilities.

## E4 release boundary

E3 proves only the control plane and persistent stub. Its `e4_release_allowed=false` capability report remains historical evidence. Later E4 isolated probes verified client-specified IDs, TaskTarget recovery, timeline effects, connection loss, and exact readback. The [E4 follow-up contract](e4-followup-task-v1.md) defines its actual limited release.
