# Progress review and planning update — 2026-10-11

> Historical snapshot. The explicit-fact, database-isolation, and dependency defects below were subsequently repaired in the [2026-10-17 record](fixes-2026-10-17.md). The text parser was later replaced by [structured answers/evidence](structured-answer-evidence.md). Preserve original observations and limits; use the [improvement plan](improvement-plan.md) for current status.

Baseline `45c846b`, compared with the 2026-10-07 assessment at `2ef4420`. This report distinguishes work actually executed here, older saved acceptance, and unverified scope.

## 1. Conclusion at the time

The project had progressed from weak reproducibility/known business-boundary defects to a reproducible foundation, tracing, and selected real-model acceptance. Original D01–D03 counterexamples were repaired and should not remain unimplemented tasks. This did not prove universally correct answers or E5 readiness.

The then-next priorities were entity-level fact binding, database isolation, actual identity ingress, and developer evidence, followed by one demonstrable business loop. No need to add multiple agents, microservices, or many write tools.

## 2. Progress since the older plan

| Area | Recorded progress | Remaining boundary at this checkpoint |
| --- | --- | --- |
| Reproduction | Tracked WWI fixtures/maps/locks/runner/CI; clean tracked-file-copy regression | Not a fresh dependency installation/full stack; no current remote CI evidence |
| I01 live authority | Per-read source/party/company/list-detail checks; reassignment regressions | Complete real mutation/delete/recreate/pagination/fault matrix |
| I02 grading | Separate tools/arguments/facts/evidence/permission/task dimensions; zero-versus-one-hundred fails | Incomplete entity binding; shared parser could jointly miss facts |
| Output gate | Buffered final text; OUTPUT_UNVERIFIED on failure; guard observation | Limited explicit-claim grammar, not arbitrary prose proof |
| I03 modes | Snapshot-only frozen fulfillment; no live registration/call | No real stock/reservation/delivery capability thereby obtained |
| Tracing | OTel/Web parent propagation/Agent/model/tool/action links/cloud; content off by default | Full ETL/MCP evidence, portable package, interrupted-content evidence |
| Real model | Historical fifteen × three, 45/45; four selected snapshot and four live cases | Not CS40/general inputs/concurrency |
| Browser | Recorded local HTTP snapshot/live UI | Full HTTPS/OIDC login/revocation/session matrix |

Code entries: [output guard](../../src/operion_etl/output_guardrails.py), [grading](../../src/operion_etl/e2_evaluation.py), [observation](../../src/operion_etl/observability.py), [runner](../../scripts/verify.sh). The historical `answer_claims.py` parser was later removed; its replacement is [evidence validation/rendering](../../src/operion_etl/answer_evidence.py). Do not link to the removed file as a current module.

## 3. Evidence actually executed here

```bash
env -u OPERION_TEST_ACTION_DATABASE_URL OPERION_OTEL_ENABLED=0 \
  PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -q
```

- Worktree: 204 tests, 180 passed, 24 skipped, no failures.
- A temporary copy of tracked files, using the existing virtual environment and copied source: identical 204/180/24. It removed ignored-WWI dependency, but was not new-machine installation acceptance.
- Section 4 used pure-memory synthetic probes, not real data writes.
- Database/model/Langfuse/browser outcomes came from existing reports and were not rerun here. The older database 24/24 was not a pass from this review.

Read local `reports/enterprise/observability/20261011/e2-final.json`, `reports/enterprise/guardrails/20261011/acceptance-snapshot-final.json`, `acceptance-live-final.json`, and `langfuse-final.json`. Scope is in [tracing acceptance](opentelemetry-langfuse-acceptance.md) and [guardrail acceptance](guardrails-langfuse-implementation.md). Ignored local artifacts cannot be the only shared durable evidence.

## 4. New findings from this review

### R01: Existing values do not establish entity ownership (P0 / I02)

Direct `verify_business_answer(tool_calls, answer)` probes used synthetic tools with `ok=True`, without the model:

| Tool facts | Incorrect answer, translated to English | Actual / required |
| --- | --- | --- |
| Order 1, USD 177.60, Draft | Order 1 amount EUR 177.60, Draft | ALLOW / reject wrong currency |
| Customer 1 zero orders; customer 2 three | Customer 1 three; customer 2 zero | ALLOW / reject swapped counts |
| Order 1 EUR 100 Draft; order 2 EUR 200 Completed | Order 1 EUR 200 Completed; order 2 EUR 100 Draft | ALLOW / reject swapped amount/state |

IDs were `wwi:sales_order:1/2`, `wwi:organization:customer:1/2`. The first probe also passed `grade_case({"tool":"get_sales_order"}, calls, answer)` with an empty failure list. This established a defect in that grading path, not every possible gold configuration.

The guard collected values across tools without sufficient entity/field/currency binding; amount parsing also lost currency semantics. These were synthetic counterexamples, not actual-user incidents.

Proposed repair then: typed `(entity_id, field, value, currency/uom, source, observed_at, evidence_pointer)` facts, structured answers/deterministic cards, constrained explanations; uncertain attribution cannot be FACTS_SUPPORTED. Do not endlessly extend regular expressions.

Acceptance: permanent three counterexamples plus valid multi-object/same-number-correct-currency/paraphrase controls; field confusion, negation, partial data, old-turn facts. Independent hand-written/source gold, not the runtime parser. Uncovered grammar remained unverified. The later closed evidence plan is documented separately.

### R02: Offline tests could inherit destructive database configuration (P0 / I16)

Static review found `scripts/verify.sh offline` did not remove `OPERION_TEST_ACTION_DATABASE_URL`. Discovery included Action tests running `DROP SCHEMA public CASCADE`; inherited DSN could therefore reach a database. CI removed it, local runner did not. This review used the safe command above and did not execute a destructive probe.

The old `scripts/test_postgres.py` only checked a `_test` database-name suffix and did not create its own database; a suffix does not prove disposability. Required an owned temporary instance/database, unique run identity, restricted account, checked cleanup, and direct-test refusal without ownership proof. Tests should prove inherited DSNs cannot connect and wrong targets fail. The subsequent isolated-container repair is in the 2026-10-17 record.

### R03: A visible trace is not reproducible developer evidence (P1 / I15)

Existing scripts covered build/unit/specialized grading but lacked one case ID across domain→real stdio MCP→scripted model→real model→Web, with expected/actual, failure layer, and rerun. Content-disabled Langfuse protected data but needed a separate explicitly authorized/redacted local evidence recorder for debugging.

Buffered output meant first SSE event was not first verified text. Add verified-text latency, false refusal/missed-gate rate, per-layer duration, and cancellation/history/recovery tests. At that checkpoint cancellation content leakage was a risk to test, not a reproduced disclosure.

## 5. Next work proposed at this checkpoint

| Batch | Work | Exit evidence |
| --- | --- | --- |
| A Correctness/test foundation | I02 binding, I16 isolation, I14 dependencies | R01 negatives/valid controls; offline cannot connect; applicable dependency findings addressed |
| B Shared evidence/identity | I15 five paths, I07 HTTPS/OIDC, I06 recovery, I04 CS40 | Normal/denied/failure/wrong/interrupted reports; real stdio; actual login/revocation; CS01–CS40 gold cases with ten holdouts |
| C Business/operations | I05 import policy/readback, I09 one exception loop, I08 baseline, I13 recovery/alerts | Query→difference/evidence→independent Task approval→readback; capacity, restore, received alerts |
| D Pilot/expansion | I10 actual use; demand-led I11/I12 | Applicable gates, ten business days, measured benefit deciding expansion |

I14 was prompted by the existing one-critical/two-high production audit; this review did not retrieve advisories or prove current exploitability. Record version/applicability, upgrades, and affected flow/build evidence. Do not upgrade unrelated packages merely for novelty.

I15 operationalized the earlier testing design, not new business scope. Proposed interface was `verify case <id> --layer domain|mcp|agent|web --mode fixture|live`, then unavailable. Expected manifest/results/events/assertions/JUnit/HTML/rerun with code/model/prompt/schema/data/scorer versions and trace/run/tool/request IDs. PASS/FAIL/SKIP/BLOCKED differ; mandatory missing layers fail release. Fixtures can replay exactly; real-model inputs/config/repeats can be retained without promising verbatim reproduction.

## 6. Business scope and interview delivery

Infrastructure did not supply complete ERP/CRM flows. Missing integration/acceptance included downstream sales delivery/returns/receivables; purchase receipt/payables; stock/reservations; opportunity/activity/follow-up outcomes; field authority/incremental changes. This did not mean the upstream products lacked those features.

Choose one loop, such as order exception→conflict/evidence explanation→human-approved internal Task→readback. Reuse the limited Task contract, not simultaneously open invoice/payment/stock/external notification tools. Do not describe current scope as complete ERP/CRM.

Interview delivery: reproducible startup, actual architecture, redacted gold cases, failure-to-fix evidence, normal/denied/outage demos, and a one-page separation of stubs/real dependencies/unverified production. Clarify existing work before adding capabilities solely for breadth.

## 7. Maintenance rule

Preserve the October 7 assessment and old stage passes as dated snapshots. This review explains their delta; the improvement plan alone maintains the current queue. Do not relist repaired D01–D03 as unimplemented or promote selected success to system-wide acceptance. I14/I16 were newly explicit work packages; I15 consolidated existing testing work; business additions remained I09/I12. Later evidence is linked, never substituted for this run's failures/limits.
