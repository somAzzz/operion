# E5: Single-operator read-only pilot and operations

Status: TECHNICAL CONTROLS IMPLEMENTED / PILOT BLOCKED. Original scope revision: 2026-09-29; current status follows the [improvement plan](../improvement-plan.md). The actual operator implements and self-checks, recording their name, date, environment, and evidence.

## Goal and entry

One actual user validates a scoped read-only service's operation, recovery, and upgrades. Entry is M1; writes stay closed. A single user/host does not establish high availability or unattended coverage. Passing E5 here establishes only this read-only scope, not multiple users or real writes.

Preparation can begin early. E5.1–E5.6 apply locally or hosted, using labeled public sample or approved private data. Write fault drills stay isolated; actual observation proves all write entry points closed. Writes require an independent approver and separate release.

| ID | Deliverable | Acceptance |
| --- | --- | --- |
| E5.1 | One actual identity/company/role, sensitive fields, source scope | Actual authorization/revocation; controlled test identities verify cache/history/field/relation isolation |
| E5.2 | Isolated deployment, pinned images/locks, private network, secrets/rotation/recovery | Clients cannot reach model/database/executor; no secrets in logs/repository |
| E5.3 | Metrics, thresholds, real receiving channel, fault runbook | Triggered alerts personally received/handled; unattended automatic pause/degradation defined |
| E5.4 | Encrypted independent backup, retention/deletion, RPO/RTO, reconciliation | Timed isolated restoration, measured loss window, no action replay |
| E5.5 | Automated five-session load, budgets, dependency failures, rollback | Measured targets or explicit pilot limits; safety unchanged; write performance remains isolated |
| E5.6 | One actual user/company, defined hours, observation | At least ten business days of service/errors/fact quality/benefit/incidents; no unresolved blocker |

## Required O01–O08

| ID | Test | Required outcome |
| --- | --- | --- |
| O01 | Actual-user revocation; test cross-user/scope/cache | Block within defined window; no leakage; test identities do not count as actual users |
| O02 | Secret rotation, invalid credentials, network/configuration | Valid recovery, old secrets fail, no disclosure |
| O03 | Model or source outage | Truthful partial/unknown outcome; no fabricated facts or unknown-write retries |
| O04 | Ledger/audit failure, stalled Worker, full disk | New writes stop; alerts delivered; recovery retains work without duplicates |
| O05 | Independent restore/remote partial success | Measured RPO/RTO; Worker disabled until reconciled; no old approval replay |
| O06 | Automated concurrency/limits/queue/timeout | Five-session resource/latency statistics; controlled overload; recovery not starved |
| O07 | Failed model/template/application release and rollback | Prior combination runs; affected evaluations pass; migration limits explicit |
| O08 | Retention/deletion/access audit/incident drill | Content expires, backup retention explained, events linked, actual owner can operate |

## Observation

Daily check unknown/failed/pending actions, sources, and backups; weekly sample facts/Task outcomes. Record legitimate volume, completion, human time, p95, model resources, API load, and sample counts. Zero traffic or universal refusal is not service quality.

Ten business days cannot establish 99.5% monthly availability; report the measured window and continue monthly measurement. Narrow load/scope or explicitly revise performance targets when needed; never relax permission/approval/idempotency.

## Exit and handoff

Deliver actual-user/scope/data policy, deployment, operations manual, O01–O08, restore/upgrade evidence, and observation report. Operator self-signs actual capability/hours/unattended limits and unverified multiple-user scenarios.

- M3: all applicable read-only requirements pass and writes are disabled.
- M4: not released by single-user E5. Self-approval is forbidden; real writes need another approver and specific acceptance. New tools remain default-deny.

## Implementation and remaining evidence

The 2026-09-20 implementation added OIDC verification, server user/tenant/company/customer/role mappings, revocation, server token forwarding, write release gates, access audit/24-hour purge, operations snapshots, Worker heartbeat/release, and strict O01–O08/observation evidence validation. See [contract](../../../contracts/e5-enterprise-boundary-v1.md) and [runbook](../../../ops/e5-enterprise-pilot.md).

I07 local Keycloak/HTTPS and synthetic protocol acceptance were added later. Bounded [session recovery](../session-expiry-login.md) and [navigation](../navigation-access.md) browser checks now exist, but do not complete the actual-user/revocation/network matrix. Preserve original CA/browser blockers in their dated reports instead of treating them as the current universal state.

Still missing a complete actual-environment package:

- Actual pilot identity, full supported-browser/revocation/network/recovery matrix.
- Personally received PostgreSQL/Worker/disk alerts and verified unattended behavior.
- Encrypted off-host backup/WAL and isolated restore establishing RPO ≤ 15 minutes/RTO ≤ 4 hours.
- Automated five-session capacity and release rollback.
- At least ten business days of nonzero actual use and operator signature.

`operion-evaluate-e5` returns `blocked`/nonzero for missing, fabricated, placeholder, or insufficient v2 evidence. Local actual use may qualify; simulated traffic does not. The 2026-09-20 v1 report remains historical and cannot satisfy v2.

## Stop and recovery

Pause affected capabilities on unauthorized/unapproved/duplicate effects, broken audit, or unknown corruption. Narrow service when backups/unknown outcomes breach agreed limits. Repair/retest and release on evidence; extensions follow [E6](e6-expansion.md).
