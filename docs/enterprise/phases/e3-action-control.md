# E3: Action control and fault recovery

Historical status: PASSED, persistent E3 stub, 2026-09-20. Owners: developer/system owner; business owner approves policy. This stage did not itself release target writes; later E4 acceptance is separate.

## Goal and entry

Before real writes, persist proposals, trusted approval, execution state, idempotency, and unknown-outcome recovery. Use fault-injection stubs; target probes are isolated and not ordinary-user tools. E0 defines permissions and E1 supplies identity contracts; final E4 release also requires E2.

| ID | Deliverable | Verification |
| --- | --- | --- |
| E3.1 | Target identity/deduplication/lookup/effects/failure probes; update CAS matrix | Actual API/config evidence; exclude unsupported capabilities or accept manual unknown handling |
| E3.2 | PostgreSQL migrations, action IDs, immutable revisions/events | Reject extras; concurrent retries yield one corresponding proposal; restart recovery |
| E3.3 | Trusted server preview/approval and REST | Bind identity/scope/digest/version/expiry; forged/replayed/replaced input fails; legitimate approval works |
| E3.4 | Deterministic separate Worker, atomic claim, lease/heartbeat/pause/preflight | No duplicate consumer effect; expired lease reconciles before resending |
| E3.5 | UNKNOWN/RECONCILING/readback/manual review with stable ID | Crash every remote commit window; events agree with effects |
| E3.6 | Append-only audit, digests, error attribution, linked compensation | No secrets; runtime cannot rewrite history; original success retained |

## Required W01–W15

| ID | Scenario | Required result |
| --- | --- | --- |
| W01 | Missing/forged approval | No remote write; denial event |
| W02 | Changed approved parameters/target/revision/effects | Old approval invalid; new preview |
| W03 | Expired/revoked/cross-user/company approval replay | No execution/disclosure |
| W04 | Permission revoked or owner invalid after approval | Pre-send conflict/cancellation |
| W05 | Concurrent duplicate request/delivery/two Workers | Stable ID; at most one intended effect |
| W06 | Response lost after target commit | UNKNOWN, exact success readback, no blind resend |
| W07 | Crash after target success before local recording | Restart reconciles without duplicate creation |
| W08 | Proven no-submission transient failure | Retry only with proof of safety or reliable deduplication, same ID |
| W09 | Expired lease while remote request continues | No potentially duplicate write; query/manual review |
| W10 | Related data/version changed | Reject/re-preview; updates without target CAS excluded |
| W11 | Pause before queue/send; cancel after send | Unsent writes stop; in-flight outcomes tracked, no false cancellation |
| W12 | Unknown fields, illegal owner, cross-company/null/absence confusion | Reject without accidental clearing or cross-scope effects |
| W13 | Ledger/audit unavailable | Stop new writes; preserve in-flight reconciliation path |
| W14 | Unprovable target outcome or multiple matches | MANUAL_REVIEW, no arbitrary selection/retry |
| W15 | Legitimate approval/execution/readback and compensation | Success; separate compensation with irreversible effects explicit |

Directly test the server without model cooperation. Inject faults before send, after remote commit, after response, and before local success persistence. Restart application/Worker at least once; use two consumers. E4 repeats applicable checks against its real API.

Approval/action pages may use stubs under the [frontend plan](../frontend-plan.md). Chat closure/refresh/device changes do not affect server actions. Decisions reference server action/revision/decision plus idempotent request ID; they cannot upload replacement parameters.

## Exit conditions

Deliver contracts, migrations/state machine, isolated deployment, target matrix, W01–W15, and recovery report. Every applicable safety item passes; unverified real-API properties become E4 blockers, not implicit release. Without reliable deduplication, implement/test a no-auto-retry/manual-confirmation path or block writing. Generic updates/cross-system transactions are excluded.

## Historical implementation and acceptance (2026-09-20)

- PostgreSQL ledger, immutable revisions/decisions/events, hash chain, idempotent proposals, trusted approval, atomic claim, leases, pauses, preflight, and recovery implemented.
- Action Service and Worker were separate processes; runtime could not update/delete history; self-approval rejected.
- Persistent `stub.followup_task` covered pre-send, response loss, post-commit crash, and pre-local-success crash without writing Twenty/ERPNext.
- W01–W15 passed; complete Python suite 81/81 and Ruff passed.
- `/approvals`, `/actions`, `/actions/{id}` passed production build and local REST integration; decisions referenced server content.
- Twenty 2.39.0 GET probes verified Task/TaskTarget schema and Task read. Client IDs, association atomicity, notifications, and connection loss were then E4 blockers.

See [E3 contract](../../../contracts/e3-action-control-v1.md) and [runbook](../../../ops/e3-action-control.md). Local package: `reports/enterprise/e3/20260920T-action-control/`. At this checkpoint real writes stayed closed until E4 probes/applicable W cases passed.

## Failure and next step

Pause executor on duplicate effects/approval bypass, repair, and rerun relevant fault windows plus valid controls. Continue to [E4](e4-followup-task.md).
