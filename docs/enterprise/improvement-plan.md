# Improvement plan: Live correctness, Agent evaluation, and justified expansion

Version: v1.6; documentation reconciled 2026-11-08. This is the single current I01–I16 implementation and remaining-work queue. It supersedes v1.5 status summaries, not their historical acceptance evidence. No new model, upstream, database, browser, or E5 acceptance is claimed by this documentation revision.

Current architecture is defined by [ADR-001](../architecture/adr-001-deterministic-agent.md), [structured answers/evidence](structured-answer-evidence.md), and the [Agent API](../../contracts/e2-agent-api-v1.md). The model selects capabilities and current evidence; domain services own facts; the server owns authorization, state, budgets, validation, and rendering. Do not extend the retired natural-language fact parser or introduce a parallel business-prose channel.

## 1. Decisions and stage relationship

The next operational goal is an E5 single-operator read-only pilot. The immediate engineering goal is to prove that data changes, relationship conflicts, source failures, ambiguity, and model mistakes still produce correct, authorized, traceable outcomes and useful task completion.

Sequence: **P0 ingress/authorization/correctness revalidation → P1 live cross-system acceptance and one complete WWI import → P2 operational readiness and justified domain depth → P3 scale and other extensions**. Prepare backup/monitoring work in parallel; actual-user access still requires applicable read-only gates.

This plan orders implementation under the [delivery plan](delivery-plan.md); it does not replace E0–E6 contracts, approval, or release gates. E0–E4 passes retain their original experimental scopes. A cross-system Agent is one Agent using Twenty and ERPNext; multiple LLM agents are not required. New WWI imports and Agent writes are accepted separately. Read-only progress never enables writes automatically.

## 2. Historical baselines and evidence limits

### 2026-09-29 review

This subsection preserves the original findings, not an unresolved defect list. The review covered source, tests, stage documents, old reports, and offline simulated probes. It did not modify real systems or rerun real-model acceptance.

| Item | Observation at that review | Limit |
| --- | --- | --- |
| Deterministic regression | 164 tests; 141 passed, 23 PostgreSQL tests skipped, no failures | Test DSN removed; skips were not passes |
| Read-only MCP | Fifteen registered snapshot tools | Tool count was not the next success measure |
| Agent | Historical fifteen cases × three repeats plus five complex Web/Agent scenarios | Fixed data does not establish live correctness or generalization |
| WWI | Snapshot customer/supplier/order queries existed; new batch not fully imported | Do not describe WWI as not integrated; see [demo readiness](../demo-readiness.md) |
| E5 | Technical controls existed, actual operational evidence incomplete | Read-only prerequisites still apply; M4 writes not released |

Original safe regression command:

```bash
env -u OPERION_TEST_ACTION_DATABASE_URL \
  PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -q
```

| ID | Original finding | Reproduction | Required invariant |
| --- | --- | --- | --- |
| D01 | Live orders reused snapshot party ownership | Simulated ERPNext changed an order to an out-of-scope customer; the old scope still received it | Revalidate current customer/supplier/company relations; reject conflicts or unverifiable identity |
| D02 | Correct tools plus an incorrect final answer passed grading | Correct zero-order payload plus an answer claiming one hundred orders produced no grading failures | Independently verify final required facts and task outcome |
| D03 | Live fulfillment used frozen scenarios | `LiveReadRepository.fulfillment_case('F01')` returned `satisfiable` with no upstream call | Frozen F scenarios cannot prove live delivery; reject or report insufficient evidence |

These were simulated reproductions, not production incidents or proven actual disclosure. The original one-off probes were not saved as complete acceptance packages. Their defects have since been repaired and regression-tested. Source: [read services](../../src/operion_etl/read_tools.py), [E2 grading](../../src/operion_etl/e2_evaluation.py).

### 2026-10-11 implementation checkpoint

- I01 revalidated source keys, target IDs, current party/company, and list/detail consistency on live reads; contact reads revalidated organization relationships. Simulated tests covered legal sales/purchase reads, reassignment, company mismatch, duplicate keys, obsolete IDs, and conflicting details.
- I02 decomposed tool choice, arguments, facts, evidence, permission, and task scoring. Its original zero-versus-one-hundred counterexample failed after repair. This checkpoint still used a limited text parser, now retired.
- I03 registered F01–F06 only in snapshot mode, rejected live calls, and labeled frozen scenarios in Web.
- Recorded regression: 184 tests, 161 passed, 23 database tests skipped; the tracked-file copy matched. Disposable PostgreSQL passed 23/23. Web TypeScript/webpack build passed. Remote CI evidence was not obtained.
- GET-only isolated checks verified selected live sales/purchase lists/details and customer/supplier contacts; wrong-company scope was denied. This was not the complete real-API mutation matrix.
- Later E2 real-model acceptance reran fifteen cases three times, 45/45. Scorer counterexamples included zero orders, seven orders, zero shortfall, negated fulfillment conclusions, and controlled upstream failure. [Tracing acceptance](opentelemetry-langfuse-acceptance.md) preserves its evidence.
- Selected snapshot/live scenarios and local HTTP browser checks followed. None replaced full HTTPS/OIDC acceptance, I04, or E5.

The later 2026-10-11 review recorded 204 tests: 180 passed and 24 skipped, including a tracked-file-copy check. These counts belong to distinct checkpoints; do not combine them into one current result.

### 2026-10-17 and 2026-10-21 follow-up

The [2026-10-17 fix record](fixes-2026-10-17.md) preserves the intermediate `business-facts-v2` repair and its evidence. [Structured evidence](structured-answer-evidence.md) subsequently replaced that parser with a closed answer plan and server rendering. Recorded selected structured snapshot/model acceptance was 4/4; its offline group was 237 tests, 213 passed and 24 skipped. It did not rerun online ERPNext/Twenty, PostgreSQL, or the full repeated E2 set.

The [ADR implementation record](../architecture/adr-001-deterministic-agent.md) describes subsequent server-owned ambiguity state, persisted candidates, execution-time gates, and cross-turn revalidation. Their existence does not prove natural-language routing quality. The original session and failure codes remain in the ADR.

[Development telemetry](telemetry-development-acceptance-2026-10-17.md) records first-class release/environment labels, content opt-in, suppressed health/ASGI noise, and bounded protocol/cloud acceptance. [Session recovery](session-expiry-login.md) and [navigation access](navigation-access.md) record bounded browser checks. Original browser/CA failures remain historical evidence; neither the failures nor later successes establish the complete E5 matrix.

## 3. Current status and task queue

The status table is authoritative for current implementation. The work-package table below retains acceptance obligations, including obligations whose original code repair is already complete.

| ID | Implemented / recorded evidence | Remaining work |
| --- | --- | --- |
| I01 / I03 | Original live-relation defects repaired; offline and selected live checks recorded; frozen fulfillment excluded from live | Full real-API change, deletion/recreation, pagination, and fault matrix in I04; no new live fulfillment claim |
| I02 | Closed `AnswerPlan`, current-run evidence binding, deterministic rendering, conflict/projection guards, and ambiguity clarification support | Full repeated real-model acceptance after contract changes; independent task-completion gold, omission tests, holdouts, false-refusal measurement, and paraphrases |
| I04 | Historical E2 45/45 and selected snapshot/live 4-case records; later structured snapshot 4/4 | Define/execute CS01–CS40, at least ten holdouts, and the live failure matrix; report versions and layers separately |
| I06 / I07 | Local OIDC/HTTPS protocol controls; bounded session-expiry/relogin and role-navigation browser records | Complete supported-browser login/logout/revocation/history/disconnect matrix, current CA trust, actual-user identity, network isolation, and recovery evidence |
| I08 | Tracing, first-verified-text metric, health/ASGI noise suppression, release/environment labels, content opt-in, and budget diagnostics | Measure p50/p95, five-concurrent-session capacity, resource/API usage, queue behavior, and release rollback; validate shared repository consistency |
| I05 / I09–I13 | No complete acceptance package for these work packages | WWI policy/import closure, justified domain capabilities, operational alert/backup evidence, actual observation, and demand-driven scale |
| I14 | 2026-10-17 production audit recorded zero findings; dependency/build repair complete | Reassess future advisories and deployed applicability; old audit is not a current security guarantee |
| I15 | Minimal case runner, real stdio MCP, scripted Agent/API, JSON/JUnit/HTML reports | Full input/output/span/request correlation, incremental timeline, real-model and browser layers |
| I16 | Offline DSN removal, owned disposable PostgreSQL container runner, and ownership guards | Obtain remote CI evidence for the applicable revision; retain isolation controls |

Default implementation and self-review belong to the project operator. Actual write approval still requires an independent approver.

| Priority / ID | Work package | Dependencies | Acceptance criteria |
| --- | --- | --- | --- |
| P0 / I07 | Identity ingress and end-to-end authority | Actual IdP and ingress; extend implemented controls | Login, expiry/revocation, trusted forwarding, no ingress bypass, backend verification, scope/roles; section 3.1 |
| P0 / I01 | Live identity/relationship authorization | Existing fixtures and simulated upstreams | Preserve D01 regression and valid controls; reassignment, company mismatch, duplicate keys, deletion/recreation fail safely |
| P0 / I02 | Evidence-backed answers and task evaluation | Existing evidence contract and independent gold | Preserve D02; wrong entity/field/currency/reference fails; valid plans work; independently measure required facts and task completion |
| P0 / I03 | Frozen/live fulfillment boundary | Existing mode gate | Preserve D03; no frozen result as live proof; absent live evidence gives refusal/insufficient information |
| P0 / I16 | Test database lifecycle | Existing runner | Inherited DSNs never connect in offline mode; wrong targets rejected; owned instance checked and cleaned |
| P1 / I14 | Dependency risk and upgrade regressions | Review applicable blockers before user access | Version/applicability conclusion and affected build/flow evidence |
| P1 / I15 | Layered developer evidence | Reuse fixtures/tracing/scoring; share cases with I04 | Minimum normal/denied/failure/wrong-answer/interrupted cases show expected/actual, layer, versions, and rerun; actual stdio evidence |
| P1 / I04 | Cross-system Agent suite | I01–I03; actual-user ingress requires I07 | Forty cases under section 4; distinguish API, domain, model, and Web execution |
| P1 / I05 | First dependency-complete WWI import | Currency and Item policies; live switch requires I01 | Two full orders/dependencies imported, independently read back, idempotently rerun, and checked by corresponding live cases |
| P1 / I06 | Browser flow/history recovery | I02; real login requires I07 | Browser asks, exceeds limits, disconnects, follows up, refreshes, and verifies isolation; HTTP/build alone is insufficient |
| P1 / I13 | E5 alert/backup preparation | May prepare now in restricted scope | Alerts actually received; independent encrypted backup and isolated recovery with applicable O evidence |
| P2 / I08 | Capacity, read efficiency, rollback | I01; measure before optimizing | Five concurrent sessions, resource/latency/API counts, isolation/timeouts/recovery, and affected rollback regressions |
| P2 / I09 | Cross-system consistency/live fulfillment evidence | I04 baseline and real field/source contracts | Add one useful domain capability at a time with deterministic facts, permission, and task evaluation |
| P2 / I10 | Actual single-user read-only observation | P0, selected I04/I06 scope, applicable E5 gates | At least ten business days of nonzero actual use; benefit/errors/fact quality/latency recorded; writes closed |
| P3 / I11 | WWI diversity and gradual scale | I05; I08 baseline before scale | Separate reconciliation/performance/Agent acceptance per scale; stop at measured boundaries |
| P3 / I12 | Sync, multiple companies, multi-step writes, industry data | Actual demand and relevant E6 gates | Independent scope/contracts/evaluation/recovery; existing write permission is not inherited |

I04 can start with existing imported records without waiting for I05. Prepare mapping/dry-run during P0 without switching to known-defective live capabilities. Simulated cases precede isolated real relationship mutations. I10 need not await I09/I11 or all WWI expansion: use a validated fixed scope, then accept each addition and revalidate affected behavior.

### 3.1 P0 identity ingress and authorization acceptance

Path: user → trusted login gateway/OIDC → Next.js → Agent/Action API → scoped domain tools → Twenty/ERPNext. The gateway is not the sole authorization point.

- Legitimate users reach allowed functions; missing/forged/expired identity or wrong issuer/audience fails. Verify logout behavior and the defined user/session revocation window.
- Strip client-supplied identity/forwarding headers. Inject only session-derived tokens; keep them server-side. Verify HttpOnly, Secure, SameSite, and CSRF as applicable.
- External clients cannot bypass ingress to reach Next.js or internal APIs. Model/database/executor are not user entry points. Prove reachability constraints in the actual topology.
- Both APIs independently validate identity and resolve tenant/company/customer/supplier scope and roles from server policy. Client/model scope cannot expand it.
- Domain tools recheck current relations. Test an authenticated user's out-of-scope queries, another conversation's history, and action requests without approval authority.
- Offline JWT tests do not replace deployed ingress evidence. Isolated tests may continue, but actual-user ingress remains gated by I07.

## 4. Cross-system acceptance and scoring

Define forty independent cases, `CS01–CS40`, without replacing existing C/F/P/A/W/O/X IDs. Write each input, gold, fault, and cleanup before implementation.

| Cases | Count | Focus |
| --- | ---: | --- |
| CS01–CS06 | 6 | Customer/supplier search, orders/details, duplicate-name selection, complete lists, zero results |
| CS07–CS14 | 8 | Party/contact reassignment, company mismatch, duplicate source keys, deletion/recreation, missing mapping |
| CS15–CS20 | 6 | Source conflicts/authority, observation gaps, amounts/units, partial data, unknown delivery |
| CS21–CS26 | 6 | Timeout, rate limit, malformed response, detail failure, pagination drift, recovery |
| CS27–CS32 | 6 | Cross-user/scope, revocation, conversation changes, note injection, misleading history |
| CS33–CS36 | 4 | Wrong quantity/amount/state, unsupported association, omitted evidence, uncertainty |
| CS37–CS40 | 4 | Follow-up, budget exhaustion, stream interruption/recovery, visible Web behavior |

Requirements:

- Declare the layer: deterministic service, simulated adapter, real GET-only API, real model, or browser. Test protected entry points directly without the model.
- Independent constants or source reconciliation produce gold, never the helper under test. Match amount, quantity, unit, state, and ownership exactly.
- Score tool choice/arguments, results, final facts, evidence/uncertainty, permission, and task completion separately. Allow equivalent routes while enforcing budgets/prohibited calls.
- Keep nonexistent, no in-scope result, not imported, forbidden, and failed read distinct; do not invent an explanation without evidence or disclose out-of-scope existence.
- Reserve at least ten cases not used for prompt tuning. Add paraphrases; replace holdouts that become regression/tuning data.
- Pin model, prompt, tool schema, data, and scorer versions. Repeat each model case at least three times, retaining every failure and sample count.
- All mandatory scope/disclosure, relationship, critical value, snapshot/live, and effect invariants pass individually. Report exploratory success separately; averages cannot hide blockers.
- Report legal task completion, false refusal, factual errors, evidence completeness, p50/p95, tokens, and tool/API counts. Freeze performance targets after baseline measurement.

Test the scorer with correct tools/wrong answer, wrong tools/fluent answer, negation, and equivalent correct answers. For the current runtime, force malformed/forged/omitted evidence plans and wrong selections rather than restoring a prose parser. A keyword hit or another model's subjective rating is insufficient.

## 5. WWI data strategy

Reuse the [first-batch selection](../../config/demo/wwi-first-batch-selection.json): sales order 66823, purchase order 2044, customer/supplier/contacts, every referenced item, and full lines. Do not truncate dependencies to increase record counts.

Resolve before import:

1. All WWI demo amounts use EUR and retain their source numeric values under mapping revision v1.2. WWI order rows have no currency code.
2. Existing stock attributes for Items 184, 193, and 204 conflict with proposed imports. Decide correct semantics and reuse/isolation without overwriting for convenience.
3. Recheck target, permission, backup, notification, and other effects under the [WWI runbook](../../ops/wwi-demo-data.md).

Sequence: mapping/plan version → dry-run → concrete approved apply under existing rules → small import → independent identity/relation/unit/quantity/amount/native-state readback → duplicate-free rerun → corresponding live Agent cases. Preserve partial success and recovery evidence.

After the first batch, expand diversity before volume. Current fifteen purchase orders all belong to supplier 7; complete orders mostly use three packaging products. Add suppliers, items/UOM, dates, duplicate names, and zero-order cases. Partial delivery, cancellation, or missing relationships need actual source evidence or a separately labeled simulated dataset.

WWI does not prove sales/purchase replenishment links from shared names/items. Live inventory, reservation, and delivery need explicit evidence. Scale in measured steps after diversity, recording line counts, scope, records read/request, latency, and resources. Full import is not itself completion.

## 6. Tools, architecture, and operations

### 6.1 Extend tools for business gaps

- Cross-system consistency: identity correspondence, field differences, authority, time, and missing evidence. Extend existing structured fields/internal services first; expose a tool only for an independent user task.
- Live order fulfillment: remaining/delivered quantities, stock, competing reservations, inbound allocation, warehouse/date/unit rules. Return insufficient information when evidence is incomplete; F cases are not live calculations.
- Every addition needs a contract, scope, provenance, completeness, budget, and fault semantics. MCP/Agent share authorization and business rules. Deterministic services calculate; the model routes and selects evidence.
- Defer generic SQL/Shell, arbitrary writes, invoices/payments/inventory adjustments, and external messaging. New writes require E6, not reuse of internal Task authorization.

### 6.2 Live reads and performance

Adapters currently scan multiple object lists and request per-order details. Measure real API calls and latency before adding on-demand reads, filtering, pagination, or caching. Avoid repeated full-batch loads as data grows.

Verify shared mutable repository consistency under five concurrent sessions, scope-isolated caches, partial refresh failure, obsolete-ID cleanup, and source-time updates. These are risks to test, not proven concurrent disclosures. Optimizations must preserve live relation checks, revocation timing, and scope.

### 6.3 Browser and E5

I06 retains actual steps, visible results, and request links: tool cards terminate; errors are understandable; queued messages can be seen/removed; follow-up succeeds after failure; refresh/history/isolation work. An unavailable browser is BLOCKED, not passed by build or SSE scripts.

I07/I13/I08/I10 reuse [E5 O01–O08](phases/e5-enterprise-pilot.md): actual-user revocation, received alerts, encrypted independent backups/recovery, five-session capacity, rollback, retention/deletion, and at least ten business days of actual use. RPO/RTO are measured; synthetic traffic does not prove user benefit.

## 7. Next batch and status maintenance

1. Run full repeated model evaluation against the current structured evidence and ambiguity contracts; score legal completion, omissions, false refusal, and language variants independently.
2. Extend implemented `scripts/verify.sh case` evidence with real-model/browser layers and request/tool/trace/evidence correlation.
3. Complete the HTTPS/OIDC/browser matrix beyond the bounded login/navigation records; recheck current certificate trust and actual identity/network controls.
4. Define/run CS40 and holdouts, then complete one WWI business loop after currency/Item policy. Measure capacity/recovery and finish applicable E5 operations before observation.

Do not list the retired parser, DSN isolation, initial tracing, first-verified-text metric, or health-span suppression as unimplemented. Their remaining task acceptance, capacity, or remote-CI evidence is separate.

Store evidence under `reports/enterprise/improvements/<run-id>/`, using the [acceptance package](delivery-plan.md#2-status-and-evidence): versions, worktree diff, environment/data mode, input, independent expected/actual, rerun, and limits. Keep old failures; do not overwrite them with a new success summary. Sensitive evidence stays out of Git; ignored local files cannot be the only team-accessible long-term evidence.

Update this status table and the enterprise index after each accepted work package. Nothing in this plan imports target data, launches a Worker, opens a new business tool, or completes E5 by itself. The local loopback HTTPS stack remains a public-snapshot/synthetic-identity development environment until the applicable actual-user gates pass.
