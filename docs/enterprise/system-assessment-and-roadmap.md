# Operion system assessment and development roadmap

> Historical snapshot: 2026-10-07, code baseline `2ef4420`. Preserve the findings, measurements, estimates, and proposed work below as evidence of that review, not today's defect list. Self-contained fixtures, D01–D03 repairs, CI, tracing, the minimal case runner, structured evidence output, ambiguity gates, and later Web controls were added afterward. See the [2026-10-11 review](progress-review-2026-10-11.md), [2026-10-17 fixes](fixes-2026-10-17.md), [structured evidence](structured-answer-evidence.md), and [current improvement queue](improvement-plan.md).

Assessment date: 2026-10-07. Intended for personal development and demo delivery, primarily Python/backend with full-stack and AI application engineering context. Translation does not constitute a new assessment or rerun.

The strongest positioning identified was a **controlled B2B trading assistant connecting ERPNext and Twenty for evidence-backed queries, exception analysis, and approved internal follow-up**. The technical foundation existed, but fact correctness, scope, reproducibility, and recovery needed stronger evidence.

Cross-system mappings, deterministic calculations, the action ledger, and fault recovery were worth retaining. Demo gaps were new-environment reproduction, result trust, and a complete business story. Enterprise gaps included downstream sales/purchasing documents, real inventory/fulfillment, financial facts, CRM process, and actual operations.

This assessment added positioning, scope, demo deliverables, and effort estimates. The then-existing improvement plan managed I01–I13; delivery rules managed E0–E6. It did not change historical acceptance or claim the planned work implemented. The current queue now manages I01–I16 separately.

## 1. Positioning and maturity at the review

Suggested description:

> I built a controlled assistant connecting ERPNext and Twenty. Stable identity maps and deterministic services query customers, suppliers, and orders. A local model works with evidence, while persistent approval and execution ledgers control internal follow-up Tasks. The project focuses on object authority, data semantics, duplicate prevention, and recovery.

Separate personal contributions from upstream ERPNext/Twenty/SGLang capabilities. Enterprise design, isolated acceptance, and real production use are distinct claims.

| Goal | Judgment at the review | Missing evidence |
| --- | --- | --- |
| Engineering practice | Useful technical depth | Clean regression, object scope, database faults, performance |
| Demo | Strong examples, incomplete reproducible release | Three demo paths, contributions, failure/recovery, tests/latency |
| Single-user enterprise read-only | Identity/operational controls existed, live correctness and operations incomplete | I01–I03, real ingress/browser, alerts/restore, ten-day use |
| Multiple-user production | Insufficient evidence | Multi-user scope/concurrency, service objectives, lifecycle, actual business |
| Complete ERP/CRM | Narrow integration/action scope | Industry-specific native document chains and ownership |

Retain modular backend, separate Web/executor, and existing databases. New features should deepen a concrete user task.

## 2. Capabilities and actual verification

### 2.1 What existed

| Layer | Implementation observed | Boundary at this checkpoint |
| --- | --- | --- |
| Data | WWI extraction, Canonical CSV, validation, mappings, readback, two demo datasets | Complete-order/currency/UOM attention; no full expansion/sync loop |
| Queries | Customers/contacts/suppliers/orders/aggregates/frozen fulfillment | Reproduced live-relation defect |
| MCP | Fifteen read-only operations | Independent entry; must share Agent authorization/semantics |
| Agent | Pydantic AI/local SGLang/allowlist/budgets/timeouts | Old grading did not establish final-answer correctness |
| Web | Next/assistant-ui/AG-UI/evidence/history/approval/actions | Needed task-oriented entry/details |
| Actions | PostgreSQL revisions/hashes/approval/leases/UNKNOWN | Actual writes limited to isolated Twenty Task |
| Identity/history | OIDC/server scopes/roles/revocation/audit | Local protocol evidence, object checks still required |
| Operations | Health, heartbeat, operations snapshots, release gate, purge | Actual alerts/restore/observation pending |

Sources: [read service](../../src/operion_etl/read_tools.py), [MCP](../../src/operion_etl/mcp_server.py), [Agent](../../src/operion_etl/agent_runtime.py), [ledger](../../src/operion_etl/action_store.py), [Worker](../../src/operion_etl/action_worker.py), [identity](../../src/operion_etl/enterprise_auth.py), [history](../../src/operion_etl/session_store.py).

Web Agent used `FunctionToolset` over shared Python business services; stdio MCP was a separate entry. Do not draw every Web read as a network MCP call.

### 2.2 Results executed for this assessment

Read code/configuration, ran offline/worktree-copy regressions, and public/simulated probes. No actual business API, model, database integration, or browser acceptance reran here.

| Check | Actual result | Meaning |
| --- | --- | --- |
| Worktree offline | 169: 146 passed, 23 skipped, zero failures | Current local data/dependencies passed |
| Tracked-file copy, same interpreter/command | 169: 44 errors, 23 skipped, exit 1 | Fresh tracked files depended on ignored inputs |
| Live ownership probe | Customer B/OTHER-COMPANY order returned as snapshot A, authorized | Current relation/company verification defect |
| Final-answer probe | Tool zero orders plus answer claiming one hundred; empty failure list | Old grader missed critical error |
| Live fulfillment probe | F01, zero upstream calls, satisfiable | Frozen scenario inherited into live; snapshot/frozen marker existed |

The copy used existing `.venv`; it tested the file set, not fresh-machine installation. Missing files included `data/canonical/wwi-v1-small-20260913-v4`, `data/test_data/companies-sample.csv`, and downstream artifacts.

[Demo readiness](../demo-readiness.md) and [gateway acceptance](gateway-acceptance.md) supplied older evidence. Gateway 38/38 protocol and no browser were historical, not passes from this review.

## 3. Priority gaps identified then

### 3.1 Current relations must enforce live authority

P0/I01: `LiveReadRepository._refresh_erpnext()` read current customer/supplier but copied snapshot relationships; order lists omitted company. Old mappings could misrepresent current scope.

Synthetic CUSTOMER-B/OTHER-COMPANY under scope A returned amount `321.00` as authorized. This did not prove an actual production disclosure.

Repair the shared domain layer: fetch current object, verify unique source key, resolve current party/company, enforce scope, then return fields. Explicitly handle conflicts, duplicates, deletion/recreation, and unverifiable relations. Apply across customer/supplier/contact/list/detail paths.

Tests require valid reads and reassignment/company/duplicate/obsolete-ID/list-detail failures. Per-object checks remain necessary after login: [OWASP object-level authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

### 3.2 Correct tools do not establish correct answers

P0/I02: [old grading](../../src/operion_etl/e2_evaluation.py) focused on payloads, forbidden fields/phrases, and nonempty output rather than systematic final quantity/amount/state/entity agreement.

The proposed approach then was typed facts, deterministic critical cards, and constrained narrative assertions. Independent gold and counterexamples were needed: correct tools/wrong answer, wrong tools/fluent answer, unsupported certainty, valid negation/paraphrase. Separately report tools, arguments, facts, evidence, permission, completion. This historical proposal is superseded by the current closed `AnswerPlan`/server-rendering contract; it does not authorize free-form business prose now.

### 3.3 Frozen scenarios versus live fulfillment

P0/I03: `evaluate_fulfillment()` already returned `data_mode=snapshot` and `frozen_fulfillment_snapshot`. Retain those markers. The gap was live inheritance of F cases without real stock/reservation/inbound/delivery/order links.

Limit frozen cases to explicit demos; incomplete actual order evidence means insufficient information. Future live capabilities use order ID/warehouse/promise date, not F01. Verify registration/result/UI/mode agree and no unauthorized real-order conclusion follows from a public scenario.

### 3.4 Reproduce without personal historical files

P0 demo delivery: local pass versus 44 tracked-copy errors required small tracked fixtures in `tests/fixtures/` or fixed-seed temporary generation. [Read tests](../../tests/test_read_tools.py) and [MCP tests](../../tests/test_mcp_server.py) were affected.

Provide locked installation, fixture preparation, tests, Web build, and one startup path. Offline regression should not need restored WWI. CI runs clean files; isolated PostgreSQL must actually execute its group, reporting missing prerequisites/skips honestly.

### 3.5 Measure performance and concurrency first

P1/P2/I08: live refresh scanned objects and per-order details; overview/detail could repeat full reads. Shared mutable repository and process-local semaphore/locks did not prove multiprocess safety.

Observed structure was not proof of a leak or measured bottleneck. Measure API volume, rows, p50/p95, queue/memory before on-demand/filter/index/immutable-request-snapshot/cache work. Cache keys include scope/company/tenant/permission version/mode without extending revocation. Multi-instance limits/locks/cancellation require separate acceptance.

### 3.6 Operations need actual evidence

I07/I13/I08/I10: loopback Keycloak start-dev/H2 and unpersisted Redis needed explicit failure/persistence boundaries. Relogin after Redis loss may be accepted if tested; identity/business state needs suitable storage.

Build from audit/heartbeat/snapshots into actual login/revocation, alert receipt, restore, rollback, and use. RPO ≤15 minutes/RTO ≤4 hours were [E5](phases/e5-enterprise-pilot.md) targets, not measurements.

## 4. Real CRM and ERP capability gaps

“Not integrated” below means no verified Operion loop at this checkpoint, not absence from the upstream product. Installed product configuration still needs verification.

### 4.1 CRM

| Domain | Coverage then | Gap/proposed next scope |
| --- | --- | --- |
| Customers/contacts | Search/detail/IDs/some relations | Lifecycle/owner/groups/merge/company history; identity/detail first |
| Leads/opportunities | No complete query loop | Source/stage/amount/close date/win-loss; opportunity/stagnation reads |
| Activities/follow-up | One controlled Task creation | Timeline/due work/load/completion reads |
| CRM→ERP | Example mapping/import | Explicit won-deal→quote/order, trading-account handoff state |
| Terms | No operating view | Quote validity/prices/discount/terms/attachments; read ERP authority |
| Sales management | Limited aggregates | Funnel/conversion/cycle/follow-up timeliness with denominators/dates |
| Service | Not integrated | Tickets/complaints/returns/SLA/history from one chosen source |
| Marketing/communication | No full loop | Outreach/preferences/unsubscribe/email/calendar later; internal follow-up first |

The review referenced Twenty Companies, People, Opportunities, Tasks, Notes, Dashboards, Workflows; reuse native objects and verify installed APIs. [Product reference](https://twenty.com/product).

### 4.2 ERP

| Domain | Coverage then | Gap/priority |
| --- | --- | --- |
| Master data | Small customer/supplier/item/contact maps | Addresses/tax/prices/UOM/warehouse/terms/history; high prerequisite |
| Order-to-cash | Sales order/lines | Quote/delivery/invoice/payment allocation/open balance/returns/credit; high read-chain priority |
| Procure-to-pay | Supplier/PO | Request/RFQ/receipt/invoice/payment/return; medium-high receipt/remaining first |
| Inventory/fulfillment | Frozen single-warehouse rule/partial quantities | Stock/reservation/availability/inbound links/transfer/safety stock; high, one company/warehouse |
| Batch/quality | No full chain | Batch/serial/expiry/inspection/nonconformance/recall by industry |
| Receivables/credit | No fact service | Balance/aging/partial receipt/credit allocation/terms; valuable read scope |
| Payables/reconciliation | Not integrated | PO/receipt/invoice differences, partial/unallocated payment; after purchasing |
| Returns/corrections | No full loop | Original relation/partial return/reversal/cancel-reopen/state propagation; exception fixtures |
| Finance semantics | Some amount/currency/UOM | Tax/discount/FX date/precision/period/GL; explain reads, ERP owns posting |
| Companies/organization | Tenant/company, one-company pilot | Switching/departments/regions/intercompany/isolation; separate acceptance |
| Manufacturing/assets | Not integrated | BOM/work orders/planning/equipment/cost/assets; defer for trading |
| Analytics | Small aggregates | Margin/turnover/on-time fulfillment/delays/collection; two fully evidenced metrics first |

Use native sales→delivery/invoice/payment and purchase→receipt/invoice/payment relations, including partial operations: [sales orders](https://docs.frappe.io/erpnext/sales-order), [purchase orders](https://docs.frappe.io/erpnext/purchase-order). Stock presence is not this order's promise: [reservation](https://docs.frappe.io/erpnext/stock-reservation).

### 4.3 Cross-system daily work

Five missing loops: source-row/batch/rule→import error→repair/rerun; incremental watermark/delete-recreate/duplicate/missed-event recovery; onboarding/offboarding/owner/approver change; exception assignment/resolution/recheck; permission-inheriting attachments/download/export.

Reuse quarantine/reports/identity/audit. Structured business reads first; add document/email retrieval only for a specific task.

## 5. Suggested business scope

### 5.1 Users and value

One-company/warehouse B2B trade for account managers/order operators/buyers. Demo uses public/synthetic data; pilot uses one authorized person/limited customers. Measure manual search/reconciliation/follow-up steps, time, and errors before comparing Operion. Resume/demo benefit numbers must be measured.

### 5.2 Three priority chains

| Chain | Task and facts | Delivery boundary |
| --- | --- | --- |
| Customer operations | Find customer/contact/order/open activity, later opportunity/invoice/balance | Demo customer→order first; later opportunity→delivery/receivables |
| Order exceptions | Demand/delivery/stock/reservation/unknown evidence→internal follow-up | Frozen demos separate; actual commercial promises stay human |
| Purchase arrival | Remaining quantity/arrival/explicit affected-demand relation | Never infer which sales order a PO replenishes from matching items |

First chain shows normal queries, second judgment/approval/recovery, third cross-domain evidence. Polish existing paths before adding opportunities/invoices/live stock; do not rewrite all three at once.

### 5.3 Minimum sales-chain model

Lead→opportunity→quote→order→delivery→invoice→payment is not one-to-one. Orders split across deliveries/invoices; payments allocate across invoices.

| Relation/fact | Requirement |
| --- | --- |
| CRM/ERP party | Stable IDs/source/verification time/conflict, no silent name join |
| Opportunity/quote/order | Explicit links; missing remains missing; old order is not a new opportunity |
| Order/delivery/invoice lines | Line-level provenance/quantity/split/partial relationship |
| Invoice/payment | ERP allocation/credit/balance definitions |
| Original/return/reversal | References/state history, no overwritten original fact |

Separate ordered/invoiced/received amounts and stock/available/reserved quantities. A single-currency limit must agree in configuration/API/UI. Aging needs cutoff/due dates; unallocated payments stay separate. Order amount minus receipts is not automatically receivables balance.

## 6. Data and architecture improvements proposed then

### 6.1 Module ownership

| Module | Responsibility | Boundary |
| --- | --- | --- |
| Adapters | Request/pagination/validation/mapping/errors | Missing response is not empty business data |
| Domain services | Permission/relations/money/quantity/state/document chain | Test without model |
| Queries | Scope/filter/cursor/completeness/source/freshness | Explain origin/coverage |
| Agent/MCP | Contracts/input/budgets/envelopes | Shared rules, separate entry tests |
| Actions | Proposal/approval/version/lease/preflight/readback | Accepted action types only |
| Web | Tasks/facts/exceptions/human confirmation | Server owns identity/authority |
| Pipeline | Rerun/import/lineage/diff/quality | Import and Agent credentials separate |

Observed sizes were about 2,016 lines in read_tools.py, 1,205 pipeline.py, 1,460 demo.py: maintenance signals, not defect counts. Split identity/order facts/adapters/fulfillment as features evolve, protected by types/contracts. The `operion_etl` package name no longer described all responsibilities, but renaming could wait for a stable release.

Reuse ledger/strict schemas/version/recovery. A new write requires preconditions/idempotency/readback/failure semantics, not merely another POST tool.

### 6.2 Common fact contract

Extend existing source/state fields with stable/source/target/company/scope IDs and field authority; snapshot/live/source-update/fetch/snapshot version; currency/tax/precision and UOM/factor/base unit; source/native/business states and mapping version; completeness/pagination/partial failure/conflict/missing/provenance; schema/rule/request versioning.

Startup time cannot replace source time. Distinguish absent/no-in-scope/not-imported/failed/forbidden internally without disclosing external-scope existence. Explicit business types reduce arbitrary dictionary guessing. The later evidence contract implements part of this direction; this historical list is not a current schema declaration.

### 6.3 Authority and synchronization

CRM owns relationship/contact/activity; ERP owns trading party/order/stock/invoice/payment. Decide overlapping fields individually, never newest whole-record wins.

Read-only difference reports precede watermarked increments/periodic reconciliation; add webhooks/durable inbox/dedup/retry/failure queues only for demonstrated freshness needs. Remote effects have no natural global transaction. Describe per-action deduplication/exact readback/UNKNOWN, not universal exactly-once. Missing target version/dedup guarantees requires explicit limits/manual conflict handling.

### 6.4 Models and resources

Keep local SGLang but make endpoint/model/context/budgets verifiable. Record weight/quantization/GPU/VRAM/startup/task latency for reproducible demo hardware. Offer model-free tool self-check and clearly labeled recorded fallback. Live inference, self-test, replay are distinct; replay is not real-model success. Compare accuracy/refusal/latency/resources on the same evaluation version before model changes.

## 7. Quality and acceptance proposals

### 7.1 Layers

| Layer | Focus | Conditions |
| --- | --- | --- |
| Pure domain | Values/UOM/state/time/scope | Every commit; synthetic/no network |
| Adapter contract | Pages/fields/duplicates/relations/delete/429/timeout/partial | Mock APIs/pinned samples |
| PostgreSQL | Claims/leases/expiry/old approval/response loss/UNKNOWN | Owned isolated database; no silent mandatory skips |
| Actual read-only API | Installed fields/version/scope/complete relations | Isolated or authorized reads |
| Agent | Tools/final facts/evidence/refusal/budgets/recovery | Pinned model/prompt/schema/data |
| Browser | Login/query/cancel/disconnect/refresh/history/roles | Actual clicks separate from protocol |
| Capacity/recovery | One-to-five sessions/outage/restart/restore/rollback | Hardware/data scale recorded |

The review proposed CI lint/offline/PostgreSQL/Web types/build/browser checks. At its baseline no tracked `.github` workflow or Web test script was found; this did not exclude external automation. Those absences were later repaired and must not be treated as current. Real-model evaluation can run in controlled release jobs; prose-only edits need no model call.

### 7.2 Agent suite

Reuse I04 CS01–CS40: six normal, eight identity, six source/semantic, six faults, six permission/context, four final facts, four session/stream. Three repeats mean at least 120 runs, retaining failures/errors. At least ten untuned holdouts; replace any used for tuning. New documents add partial delivery/invoice/payment/return/precision/stale-relation cases. Independent source/constants produce gold.

### 7.3 Proposed metrics, not achieved results

| Metric | Goal/report |
| --- | --- |
| Reproduction | Clean file set and clean install, consistent results/explicit skips |
| Critical invariants | Zero unauthorized/wrong-relation/critical-value/unapproved/duplicate effects in the specified suite |
| Legitimate tasks | Mandatory cases individually pass; exploratory completion/sample count separate |
| Completeness | Full required dependencies/lines, reconcilable aggregates |
| Evidence | Object/mode/source/time; visible missing information |
| Performance | Tool/end-to-end p50/p95, queue, tokens, API volume, concurrency |
| Initial experiment | Try tool p95 ≤3 seconds/end-to-end ≤30, then freeze by measured hardware/task |
| Recovery | Terminal timeout/disconnect, later request recovery, duplicate-free unknown reconciliation |
| Benefit | At least ten business days of nonzero actual use/manual comparison/errors/false refusal |

These exploratory 3/30-second targets did not replace the operating plan's 5/60-second proposed limits. Neither was a measured commitment. Do not hide scope errors in average success or claim usefulness by refusing everything. Ten days do not prove annual availability. The then-observed 90-second profile limit was a protection ceiling, not a user-experience target or today's universal default.

## 8. Frontend and demo

### 8.1 Task-oriented UI proposal

Build on evidence/history/actions with customer operations, order exceptions, and purchase arrival entry points plus free query. Fixed customer/order views show contacts/orders/state/source/exceptions and link to proposals/execution. Tables need filters/stable sort/real pages. Lead with outcome/missing evidence; expandable diagnostics hold IDs/parameters/versions. Approval shows exact object/content/effects/version/expiry and useful next steps.

No screenshots/interaction audit were performed here. These were code-informed proposals, not visual/accessibility acceptance. Later test keyboard/focus/status announcements/small tables/errors.

### 8.2 Ten-minute demonstration

| Minutes | Demo | Evidence |
| --- | --- | --- |
| 0–1 | User, systems, personal scope | Positioning/business understanding |
| 1–3 | Customer selection/contact/orders/source | Cross-system facts |
| 3–5 | Changed ownership/scope or unknown delivery | Permission/uncertainty |
| 5–7 | Isolated proposal/different-identity approval/readback | Controlled effects/separation |
| 7–9 | Response loss/duplicates/reconciliation | Distributed-effect recovery |
| 9–10 | Tests/latency/limits | Engineering tradeoffs |

WWI query and E2 action profiles share ports and need planned switching or a labeled recording. Simulated roles demonstrate technical separation, not an actual independent human approver.

### 8.3 Release materials

README introduction/one recommended startup, actual architecture page, three pinned scripts, short video/backup recording, test/evaluation/performance reports, limits/contributions. Four short decisions: why retain ERP/CRM, deterministic business facts, UNKNOWN, and modular monolith. Retain data origin/licenses; publish no credentials/private business data.

| Demo question | Evidence to prepare |
| --- | --- |
| Why not arbitrary model SQL? | Contracts/minimum fields/scope |
| Why does login not stop all unauthorized reads? | Old mapping versus current relation probe/fix |
| What if write succeeds but response is lost? | UNKNOWN/exact ID/readback/dedup |
| What if data changes after approval? | Revision/binding/preflight |
| How is correctness established? | Independent gold, scorer counterexamples, final facts, holdouts |
| How do multiple users work? | Scope/concurrency/limits/locks/multiprocess limitations |
| What is personal work? | ETL/maps/domain/protocol/history/ledger/evaluation; upstream separately |

Backend demos emphasize authority/transactions/idempotency/SQL/testing; AI emphasizes facts/evaluation/protocol/budgets; full-stack adds interaction/recovery. Resume numbers must be actual measurements.

## 9. Historical phased estimates

### 9.1 Assumptions

One familiar developer with working model/business environments: demo-ready version **80–130 hours**, roughly **6–9 weeks at fifteen hours/week**. Individual stages summed to 76–122 hours plus integration margin. New machines/external outages/major rework were extra.

One deeper chain added **60–100 hours**; operations **30–50 hours**, plus at least ten business days of actual observation. Under deadlines, cut new features, not correctness/reproduction. These estimates are historical plans, not completed labor or current fresh estimates.

### 9.2 Demo-ready version

| Stage | Hours | Work | Exit/dependency |
| --- | --- | --- | --- |
| A Reproduction | 8–12 | Fixtures, hidden dependencies, offline entry, versions/modes | No prerequisite; tracked-copy pass |
| B Correctness | 24–40 | I01 relations, I02 grading, I03 modes, negatives/valid controls | A baseline; three probes permanently repaired |
| C Integration/demo | 24–40 | Isolated DB, CS40/model repeats, browser/I07, performance | B; mandatory layered evidence |
| D Release | 20–30 | Task views/evidence, startup/self-check, video/decisions/scripts/summary | A–C; another clean environment and ten-minute demo |

Operator implements/self-reviews actual diffs/cases. Prepare documentation/video/business questions during waits; independent real-write approval remains. If actual APIs are unavailable, deliver a labeled snapshot/simulated demo build with live disabled/unaccepted; it cannot receive enterprise pilot release.

### 9.3 Business-depth version

60–100 hours for one chain, not both complete sales and purchasing. Prefer customer operations with opportunity/activity/delivery/invoice/balance reads, or fulfillment/arrival for supply-chain needs.

| Package | Deliverable | Exit |
| --- | --- | --- |
| Rules | Roles/authority/state/relations/scope/amount/date | Explain every field with normal/exception examples |
| Data | Normal/partial/missing/cancel-return/partial payment | Complete dependencies and source/mode labels |
| Adapters | Read APIs/IDs/line links/time | Independent source agreement, truthful denials/partial failures |
| Agent | Summary/exception with existing capabilities first | New independent gold on required facts/evidence |
| Views | Customer/order chain/exception/provenance | Understandable without technical parameters |
| Follow-up | Existing Task; new action separately contracted | Approval/dedup/version/disconnect recovery |

Invoice/payment initially read-only; posting/refund/stock/external email require separate release.

### 9.4 Enterprise read-only pilot

30–50 operations hours plus at least ten business days. Start on an accepted limited read scope without waiting for every expansion:

1. Actual identity/scope/browser/network acceptance.
2. I13 received alerts/off-host backup/isolated restore with measured loss/time.
3. I08 five sessions/degradation/rollback, explicit single-host/multi-instance limits.
4. One actual user/few customers recording requests/errors/time/unknowns/benefit daily.
5. Applicable O01–O08 then release only evidenced reads; writes still independent.

Add certificate/key rotation, identity persistence, store/backup retention, access-audit export, minimum accounts, upgrade compatibility. Bind operations/restore evidence to one release/schema.

### 9.5 Demand-led expansion

Incremental sync/multiple warehouses/companies/users/reporting/service/writes belong to E6. Specify benefit/authority/permission/faults/recovery/regressions. Change the model/product positioning for manufacturing/POS/industry traceability only when needed.

## 10. First batch proposed then

20–30 hours to stabilize reproduction and the first correctness repair, not finish all P0:

| Order | Task | Reviewable output |
| --- | --- | --- |
| 1 | Freeze baseline/three probes | Version, simulated inputs, independent expected/actual, old evidence |
| 2 | Self-contained fixtures | Tracked copy passes without personal history |
| 3 | Repair current customer/supplier/company I01 | Reassignment rejection/valid controls; shared MCP/Agent |
| 4 | Permanent wrong-answer/live-frozen regressions | Accurate before-fix failure matching probes |
| 5 | Remaining I02/I03 and status | Carry unfinished work forward with disabled scope |
| 6 | Owned PostgreSQL/CI baseline | Actual database execution/clean install evidence |

I05 mapping/dry-run could proceed, but currency/USD assumption/EUR target/stock-Item conflicts needed policy first. Complete readback/idempotent rerun after import; volume is not semantic correctness. Much of this first batch was later implemented; consult current status before scheduling it again.

## 11. Risks and scope

| Risk | Effect | Response |
| --- | --- | --- |
| Expansion outruns evidence | More tools, unproven facts | One chain, gold/scope first |
| Local hardware | Demo startup/latency | Document resources, model-free check, labeled recording |
| Upstream change | Adapter/readback breaks | Pin accepted versions and test contracts |
| WWI semantics | Currency/delivery/replenishment misunderstanding | Assumptions/unknowns and separate simulation |
| Shared state/cache | Hidden scope/concurrency issues | Test/isolate before optimizing/scaling |
| Simulated-only evidence | No actual-user proof | Separate layers and nonzero actual enterprise use |
| Duplicate/stale docs | Narrative/code disagreement | One current queue and shared release evidence |

Prioritize correctness/reproduction/one chain. Defer unjustified microservices/Kubernetes/multi-agent/vector stores/full ERP UI replication/full sample import. Sync needs freshness demand; retrieval needs an actual document/email task; extra agents need a demonstrated single-agent bottleneck. Measure benefit and maintenance.

Each package records state/dependency/reviewer/version/evidence/unexecuted layers. Invariants pass individually; performance/benefit include distributions/counts. The proposed next assessment followed stage B to check repaired probes/reproduction/database before selecting C.

## 12. Verification and references

Actual safe command used for this review:

```bash
env -u OPERION_TEST_ACTION_DATABASE_URL \
  PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -q
```

Tracked-copy method used `git ls-files -z`, copied ordinary tracked files to a temporary directory, and used the existing interpreter with copied source and the same unittest command. No ignored data, real business changes, or actual API access.

| Probe | Input | Observed | Required after repair |
| --- | --- | --- | --- |
| I01 | Same source order, snapshot A, live B/OTHER-COMPANY, scope A | A/321.00/authorized | Deny or unverifiable relation |
| I02 | Tool zero orders; answer claiming one hundred | `grade_case` returned `[]` | Fail critical mismatch |
| I03 | Live F01 with counted fake client | Zero upstream calls, satisfiable, snapshot/frozen markers | Demo-only; no live proof |

Repository references: [queue/original findings](improvement-plan.md), [gateway scope](gateway-acceptance.md), [demo evidence](../demo-readiness.md), [human responsibilities](../human-functions-agent-map.md), [E5 gates](phases/e5-enterprise-pilot.md), [action contract](../../contracts/e3-action-control-v1.md), [Task contract](../../contracts/e4-followup-task-v1.md).

External references above were official ERPNext/Twenty/OWASP material used in the original assessment, not a current-version audit. Installed APIs still need acceptance. This deliverable was assessment/planning; later implementations and their separate results are linked in the historical notice, never backfilled into this run.
