# Guardrails and Langfuse: Implementation and acceptance

> Historical record, 2026-10-11. The parser below was superseded by [structured answers/evidence](structured-answer-evidence.md). Later explicit-fact, test-isolation, and dependency repairs are in the [2026-10-17 record](fixes-2026-10-17.md). Original results/limits remain unchanged.

Scope was runtime checking of read-only answers and regression evidence for existing safety gates. Identity, object permission, approval, ledger, and Worker remained enforcement boundaries. Langfuse did not grant release and no write scope expanded.

## Staged implementation

| Stage | Deliverable | Acceptance |
| --- | --- | --- |
| 1 Baseline | Inventory auth, filtering, scope, modes, write gates, offline grading | Offline checks; covered/uncovered scope |
| 2 Pre-publication facts | Shared text extraction, buffered answer versus server tool evidence | Wrong counts/money/entity/state/fulfillment not published/saved; valid answers visible |
| 3 Adversarial observation | Content-free OTel guardrail child spans and actual execution tests | Same trace, stable nonsensitive reasons, local verdict |
| 4 Real selected scenarios | Imported WWI/public snapshot, running SGLang/FastAPI/AG-UI; optional real GET-only sources | Independent expectations/results/history, visible Langfuse guards, explicit snapshot/live |
| 5 Overall | Offline, isolated PostgreSQL, Web, selected real model, trace UI/privacy | Commands, versions, expected/actual, untested scope |

## Design used at the time

Explicit order counts, money, canonical IDs, state, and fulfillment claims were compared to successful server tool results. Unsupported/conflicting claims blocked publication; safe uncertainty could remain visible. Tool events continued, text waited for model completion, and failure emitted `OUTPUT_UNVERIFIED` without successful history.

ALLOW/DENY/UNKNOWN were output verdicts, not HTTP status, source outcomes, or Worker UNKNOWN. Spans held guard name/verdict/reason/policy only. Existing unittest/CI remained release gates; Langfuse observed via OTel → Collector, with Scores API copies and no second exporter.

The parser covered only deterministically recognizable explicit claims, not all implicit reasoning/pronouns. That limitation is historical, not the current output design. Pagination `partial` could still have filtered `total_count`; `full_source_history=undetermined` prohibited complete-history claims. Live meant the current authorized/imported dataset, not all source history. Output guards did not replace write controls.

## Historical results (2026-10-11)

| Check | Evidence | Result |
| --- | --- | --- |
| Baseline | Offline 204: 180 passed, 24 skipped; isolated postgres:16 24/24 | PASS |
| Publication gate | `tests/test_output_guardrails.py` and `tests/test_agent_app.py` rejected wrong count/money/entity/state/fulfillment/failure text in SSE/history | PASS |
| Web | TypeScript/production; local snapshot/live browser interactions | PASS |
| Real snapshot model | qwen3.8-27b, `demo-wwi-v1`: customer 65/10 orders, order 66823/USD 177.60, write denial, injected wrong count, 4/4 | PASS; `reports/enterprise/guardrails/20261011/acceptance-snapshot-final.json` |
| Real live sources | `TWENTY_API_KEY_READ_ONLY` and `ERPNEXT_API_KEY_READ_ONLY` from `.env`; independently verified imported `wwi-v1-small-20260919-e1`: customer 11/1 order, 73595/EUR 2160.0/Draft; model 4/4 | PASS; `reports/enterprise/guardrails/20261011/acceptance-live-final.json` |
| Actual browser | Local Web→Agent→live sources→SGLang; customer 11/1 order, `live · public_sample` evidence card, 73595/EUR 2160.0/Draft | PASS, local `http://127.0.0.1:3002/` |
| Langfuse | Eight final traces with GUARDRAIL children linked to `operion.agent.run`; injected count `deny / ORDER_COUNT_MISMATCH`; guard Input/Output empty; live Boolean `operion_guardrail_acceptance` scores | PASS; [denial trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/2e60253665108c44205f90c886ede3ad) |

Gateway Agent/Web were rebuilt/healthy; gateway remained snapshot while live acceptance used a separate local read-only Agent. Langfuse 8/8 API evidence stayed in `reports/enterprise/guardrails/20261011/langfuse-final.json`; the final denial UI showed `operion_guardrail_acceptance: True`, GUARDRAIL, deny, and ORDER_COUNT_MISMATCH.

Live expected amount/state came from ERPNext; Twenty independently verified identity. WWI source `open` was not substituted for live Draft. Ignored reports retained answer/events/tools/status/trace IDs. Targets contained other datasets; acceptance covered only selected authorized samples, with full source history undetermined.

Initial real-model parsing missed the literal Markdown-bold form `**1** sales order`; snapshot runs also exposed amount-format/negation issues. Repairs added counterexamples and final selected runs passed. Expected DENY counted as test PASS; cloud scores copied local verdicts, never authorized runtime behavior.

## Rerun entry points

```bash
scripts/verify.sh offline
scripts/verify.sh web
OPERION_OTEL_ENABLED=1 OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces PYTHONPATH=src .venv/bin/python scripts/accept_guardrails.py --output reports/enterprise/guardrails/snapshot.json --publish-langfuse-scores
OPERION_OTEL_ENABLED=1 OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces PYTHONPATH=src .venv/bin/python scripts/accept_guardrails_live.py --output reports/enterprise/guardrails/live.json --publish-langfuse-scores
```

These scripts have since migrated to the current evidence contract; commands do not recreate the retired parser. Use new report paths to preserve old evidence. Requires SGLang, Collector, business systems, and explicit scoring credentials in `.env.langfuse.local`. Live scripts load only named read keys, never admin keys or write endpoints.

At this checkpoint HTTPS browser acceptance was blocked by untrusted local CA; successful UI checks used localhost and did not replace I07/E5. Production audit then had three findings (two high, one critical); functional acceptance did not clear them. Later repair/CA/browser evidence is separate and does not rewrite this history.
