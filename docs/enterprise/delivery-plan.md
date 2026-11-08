# Delivery plan and acceptance rules

Version: v1.2; documentation reconciled 2026-11-08. These are acceptance rules. Current implementation and remaining work live in the [enterprise index](README.md) and [improvement plan](improvement-plan.md); historical passes keep their original scope.

## 1. Dependencies and milestones

Main path: E0 → E1 → E2 → E3 → E4 → E5 → justified E6.

E3 state-machine/stub development may overlap E1/E2, but real writes require E3 acceptance. Web conversations enter at E2; approval/action pages may use E3 stubs before E4 connects real proposals/writes. Prepare E5 identity, backup, and operations from E0. After E2 and applicable E5 identity/scope/network gates, begin single-user read-only observation with writes closed. E6 synchronization preparation may start when needed, but cannot substitute for current acceptance or use Agent credentials for ETL.

| Milestone | Required passes | Exposed capability |
| --- | --- | --- |
| M1 Verifiable read-only demo | E0, E1, E2 | Public-sample overview and frozen fulfillment checks |
| M2 Controlled-write demo | M1, E3, E4 | Internal follow-up Task loop |
| M3 Single-user read-only pilot | M1 and E5 read-only gates | One actual user, explicit public-sample/approved private-data scope; no writes |
| M4 Controlled-write pilot | M2, E5 read-only gates, independent approver, write-specific acceptance | One write capability within approved users/scope/hours; not released by the single-user phase |
| M5 Expansion | Relevant E6 item | Only individually accepted additions |

Deliver reproducible subgoals. Creating directories, starting services, or a model saying it is done is not acceptance. Ordinary implementation does not need repeated human confirmation. Stage release is an evidence-based project decision; business actions still require exact approval.

## 2. Status and evidence

Subgoal states: `PLANNED` → `IN_PROGRESS` → `READY_FOR_REVIEW` → `PASSED`. Use `BLOCKED` with cause, owner, and exit condition. Relevant version changes require `REVALIDATION_REQUIRED`; do not silently reuse an old pass.

Save evidence in `reports/enterprise/<phase>/<run-id>/`. Sensitive artifacts stay out of Git. Commit redacted summaries and controlled references; ignored local files are not a durable shared evidence store.

Each acceptance package contains at least:

```text
manifest.json       commit, worktree diff summary, component versions, config, time, environment
acceptance.md       per-goal/case conclusions, evidence, limits, reviewer
results.json        automated expected / actual / pass / fail
reproduce.md        actual commands, data prerequisites, reproduction and cleanup
artifacts/          redacted responses, readback, events, screenshots, fault/recovery evidence
```

No passwords, auth headers, or complete private-customer conversations in reports. Cleanup targets identifiable test records through supported business operations; never empty a shared business database merely to repeat a test.

| Per-item field | Requirement |
| --- | --- |
| Goal and case ID | For example E3.4 / W06, linked to the contract |
| Version/environment | Code/model/template/policy/backend versions and isolation |
| Prerequisites | Permission, snapshot, action state, injected fault |
| Operation | Exact request/command, not merely “tested” |
| Expected | Return value, transitions, target effect count |
| Actual | Observation, readback, events, and errors |
| Verdict | PASS / FAIL / BLOCKED; no vague “mostly passed” |
| Ownership/review | Implementer, reviewer, date; disclose self-review |
| Limits | Uncovered scope, target limitations, next step |

## 3. Unified acceptance rules

1. Authorization bypass, unapproved writes, duplicate effects, and approval-content substitution block release regardless of user count.
2. Critical values match independent expectations; facts have provenance and data time. Current answers use the [structured evidence contract](structured-answer-evidence.md), not free-form business prose.
3. Do not remove cases or refuse every task to obtain a pass. Report legitimate completion and dangerous-path prevention separately.
4. Writes require readback and agreement between ledger and target effects. Unknown outcome is neither success nor confirmed failure.
5. Performance, recovery, and retention are targets or explicitly accepted limitations; unmeasured is not achieved.
6. All mandatory applicable items pass before PASSED. Explain inapplicable items with scope and responsible confirmation; applicable safety requirements cannot be waived.
7. Narrow scope when backend capabilities are missing; prompts or gateway-local locks do not establish target guarantees.
8. Schema legality, evidence support, and user-task completion have separate assertions. Force incorrect model calls/output at protected execution entry points.

## 4. Cross-stage verification catalog

| Category | IDs/scope | First required |
| --- | --- | --- |
| Business baseline | C01–C03, F01–F06 | E1 deterministic facts; E2 selection of evidence |
| Read safety/errors | P01–P03, A01–A03 | E1/E2; preserve original IDs |
| Execution/fault safety | W01–W15 | E3; repeat applicable cases against E4's real isolated API |
| Operations/recovery | O01–O08 | E5 |
| Expansion | X01 onward by synchronization/update/composite action | E6 |
| Live cross-system/answer quality | [CS01–CS40](improvement-plan.md#4-cross-system-acceptance-and-scoring) | Current E1/E2 revalidation; reuse for new data/capabilities |

The [minimum demo](../minimum-demo.md) defines the original fifteen cases. Do not overwrite old IDs. Repeat model cases at least three times on pinned versions, retaining every result. Server invariants judge dangerous effects; model text alone is insufficient. Directly test every protected entry point without relying on model refusal.

## 5. Scheduling and work organization

Schedule by dependencies and evidence, not unexamined fixed-week promises. Estimate E1/E2 after E0 based on adapters, identity, target deduplication, and GPU capacity. Estimate writes after E3 probes.

Each task includes one contract/feature change, relevant checks, actual-diff review, and status updates. Dependency/model/data changes trigger affected checks, not purposeless repetition of all experiments.

Completion is M1/M2/M3/M4/M5, not completion of every optional E6 item. E0–E4 passes remain experimental. Follow the [current queue](improvement-plan.md): P0 ingress/authorization/evidence/task correctness → P1 live acceptance/WWI closure → P2 operations/domain depth → P3 scale. Prepare backup/alerts in parallel; old reports do not release changed behavior.

[E5 single-user read-only](phases/e5-enterprise-pilot.md) remains the next operational milestone. It does not require all WWI expansion or optional tools. Multiple users, unattended operation, and M4 writes require independent acceptance.
