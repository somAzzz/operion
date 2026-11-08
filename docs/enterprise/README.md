# Enterprise architecture, implementation, and acceptance index

Documentation revision: 2026-11-08. E0–E4 retain their historical experimental acceptance scopes. Current code includes structured evidence answers, ambiguity selection gates, budget diagnostics, enterprise identity controls, and the minimal developer runner. E5 actual-user operational evidence remains incomplete; real-data writes are not released.

A document, a running service, and an old passing report are different kinds of evidence. This documentation reconciliation adds no new runtime acceptance.

## Read current guidance first

1. [ADR-001](../architecture/adr-001-deterministic-agent.md) and [Agent / MCP boundaries](../agent-boundaries.md): ownership of business facts, execution, and model behavior.
2. [Structured answers and evidence](structured-answer-evidence.md): `present_answer`, `AnswerPlan`, `EvidenceRegistry`, and deterministic rendering. Free-form business prose is not an output fallback.
3. [Agent API](../../contracts/e2-agent-api-v1.md): authentication modes, ambiguity selection, limits, budget diagnostics, and public errors.
4. [Improvement plan](improvement-plan.md): the single current I01–I16 status table and remaining queue. Full repeated model acceptance, CS01–CS40/holdouts, live fault matrices, and E5 gates are separate pending work.
5. [Operating plan](operating-plan.md), [delivery/acceptance rules](delivery-plan.md), and [frontend plan](frontend-plan.md): architecture, operational targets, and release criteria.
6. [Developer observability/testing](developer-observability-and-testing.md): implemented `scripts/verify.sh` commands and the explicitly proposed full evidence timeline.

Current Web guidance includes [navigation access](navigation-access.md) and [session-expiry login](session-expiry-login.md). Both have bounded browser records; these do not establish completion of the full HTTPS/OIDC/revocation/network matrix or E5 observation.

Tracing configuration lives in the [OTel/Langfuse runbook](opentelemetry-langfuse-runbook.md). [Development telemetry acceptance](telemetry-development-acceptance-2026-10-17.md) records content opt-in, release/environment labels, health-span suppression, and cloud protocol checks. Capacity and release/recovery measurements remain pending.

I07: [local gateway acceptance](gateway-acceptance.md) and [runbook](../../ops/auth-gateway.md). The local stack uses synthetic identities and public snapshots. Original CA/browser blockers and later bounded browser checks must be read in their dated scopes; do not turn either into blanket acceptance or a blanket statement that no browser work exists.

## Stage status

| Stage | Plan | Deliverable | Status and limits |
| --- | --- | --- | --- |
| E0 | [Environment, permissions, recovery](phases/e0-baseline.md) | Verifiable versions, scope, and recovery | PASSED experimentally; [historical summary](e0-baseline-result.md) |
| E1 | [Data and read tools](phases/e1-read-tools.md) | Source-backed, scoped domain facts | PASSED original scope on 2026-09-19; later capabilities require their own evidence |
| E2 | [Read-only Agent/evaluation](phases/e2-read-agent.md) | Original overview/fulfillment and fifteen cases | Historical 7/7 compatibility and 45/45 model baseline; selected structured-answer acceptance is recorded separately, not a replacement full rerun |
| E3 | [Action control/recovery](phases/e3-action-control.md) | Persistent proposals, independent approval, idempotency | PASSED persistent-stub scope on 2026-09-20 |
| E4 | [One controlled write](phases/e4-followup-task.md) | One internal Twenty follow-up Task path | PASSED isolated public/simulated demo scope on 2026-09-20 |
| E5 | [Single-operator read-only pilot](phases/e5-enterprise-pilot.md) | Actual user, alerts, recovery, release, observation | Technical controls implemented; actual operational evidence and ten-business-day use incomplete; writes remain closed |
| E6 | [Synchronization and expansion](phases/e6-expansion.md) | Individually justified extensions | Start only when needed and accept each new scope separately |

## Historical evidence

Keep original dates, baselines, failures, counts, skips, source modes, and limitations. Translation and current-guidance corrections do not revalidate old results.

- [2026-10-17 fixes](fixes-2026-10-17.md): old explicit-fact parser, cancellation, dependency repair, isolated PostgreSQL, and minimal runner. The parser was subsequently replaced by structured evidence.
- [2026-10-11 progress review](progress-review-2026-10-11.md): reproduced gaps and the state before those fixes.
- [2026-10-07 system assessment](system-assessment-and-roadmap.md): historical engineering/interview assessment and ERP/CRM capability gaps.
- [Guardrails/Langfuse implementation](guardrails-langfuse-implementation.md) and [initial tracing acceptance](opentelemetry-langfuse-acceptance.md): earlier selected snapshot/live/model/cloud evidence, not current universal correctness.
- [Minimum demo](../minimum-demo.md): original C/F/P/A cases and fixed fulfillment semantics.
- [Human workflows](../human-functions-agent-map.md): human/Agent responsibility split.
- [Data pipeline runbook](../../ops/data-pipeline.md): ETL preparation and recovery. ETL credentials and loading functions are not Agent tools.

Current contracts define behavior. The improvement plan defines the remaining queue. Historical reports establish only what was observed in their recorded versions and scopes. If these disagree, document and resolve the discrepancy rather than expanding authority or claiming a new pass.
