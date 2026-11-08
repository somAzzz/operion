# E6: Synchronization and capability expansion

Status: Start only when needed. Business owner establishes value; developer/system/operator own applicable items. Current selection/status follows the [improvement plan](../improvement-plan.md).

## Goal and entry

Expand verified loops for actual demand, one independently scoped/contracted/tested/released capability at a time. Normally reuse M4 controls; read/sync expansion satisfies its actual E0/E1/E5 risks. Lack of a model does not exempt integration writes from data safety.

| ID | Entry and deliverables | Core tests/exit |
| --- | --- | --- |
| E6.1 | Real update demand; field authority, stable maps, watermarks/overlap, recovery/reconciliation | X01 duplicates/out-of-order do not duplicate creation; X02 preserve non-authoritative human fields/no loops; X03 explain partial success/deletes/watermark recovery |
| E6.2 | More reads/companies; business definitions, company/currency/UOM/scope/budgets | X04 isolation; X05 duplicate names, currency/unit/time gaps; legitimate aggregation and denials |
| E6.3 | Controlled customer updates; fixed fields, diff/preview, target CAS, compensation | X06 no lost concurrent update after approval; X07 null/absence/protected fields; no automatic update without backend CAS |
| E6.4 | CRM→ERP handoff/composite actions; per-step action/dependency/partial state/compensation/manual review | X08 recover failure after any commit; X09 restart does not repeat completed steps; people handle irreversible effects |
| E6.5 | Manufacturing/pharma data, domain contracts, license/simulation labels | X10 BOM/UOM/effective-date gold; X11 insufficient drug-match evidence returns candidates, no invented risk conclusion |

X01–X11 are seeds, not executed passes. Define input/expected/faults before implementation. Unselected items stay PLANNED without blocking other accepted capabilities.

## Synchronization-specific design

Separate sync and Agent identities. Sync cannot modify schema/permissions. Define directional field ownership/conflicts with source/event/batch/mapping/target state. Initially do not propagate physical deletion; choose explicit review/deactivation policy.

Advance watermarks only after target commit is confirmed or errors are durably recoverable. Stable deduplication covers pages/overlap/reruns. Reconcile identity, key fields, and native state, not counts alone. Sync and Agent writes share business conflict rules, not model approval conversations.

## Admission for new write tools

Business value → fixed object/field/scope/effects → target permission/deduplication/concurrency probes → proposal/approval/compensation → W regressions → isolated readback → limited pilot → independent release.

Internal Task authority does not permit arbitrary creation or reuse of old approval for another type. Posting, payment, stock adjustments, and external sending need independent business design/responsibility even after another E6 item passes. Permission/schema changes and arbitrary SQL/Shell remain unavailable to the business Agent.

## Exit

Each enabled item has a capability card: owner, scope, contract/policy versions, cases, actual evidence, recovery, metrics, limits, release date. Pause per tool/tenant without unnecessarily stopping stable capabilities.

Update the [index](../README.md) and contracts; rerun affected original fifteen/W/O cases. Unfinished optional expansion does not revoke M1–M4; underlying changes that break old guarantees do require reacceptance.
