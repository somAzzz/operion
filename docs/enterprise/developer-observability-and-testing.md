# Operion developer observability and testing

Date: 2026-10-07; updated 2026-10-17. OTel/Langfuse, bound explicit-fact checks and the minimal developer case runner are implemented. `scripts/verify.sh case` writes JSON, JUnit and HTML evidence for domain, scripted Agent/API and real stdio MCP checks. `offline` removes inherited test DSNs; `postgres` creates and removes an isolated Docker container. See [implementation and validation](fixes-2026-10-17.md). The full content/event timeline, real-model and browser layers below remain proposals.

The target developer experience is **run one case, see every boundary it crossed, compare expected and actual results, and reproduce the failure at the smallest relevant layer**. Use one case definition across domain services, MCP, the Agent, and the browser. Preserve which dependencies were simulated and which were real.

This guide complements the [system assessment](system-assessment-and-roadmap.md) and implements the testing direction of I01–I04, I06–I08 and I13 in the [existing improvement plan](improvement-plan.md).

## 1 What exists and what is missing

| Existing implementation | Reuse it | Add or correct |
|---|---|---|
| `AgentDependencies.tool_calls` and `_record_tool` | Arguments and returned results | Invocation IDs, start/end events, duration, exceptions, guard decisions; consolidate manually recorded tools too |
| SQLite `agent_runs` | Run ID, status, token totals, timestamps | Trace correlation is implemented; add version manifest, evidence references and incomplete/crashed execution classification |
| Trusted message history | Model requests/responses from completed or cancelled runs | Per-request evidence for interrupted/error paths; content handling policy |
| E2 JSON evaluations | Cases, repeated runs, tool payloads, final answers | Decomposed final-fact scoring is implemented; strengthen entity/field/currency binding, independent counterexamples, holdouts and per-layer reports |
| MCP tests | Tool names, schemas, annotations, in-process calls | Real stdio client/server handshake and calls; malformed requests, lifecycle and correlation |
| Complex interview script | Web → Agent → SGLang → tools, SSE ordering | Persist events, full authorized answer, assertion differences and links to spans |
| Action ledger and W01–W15 | Approval, revision, leases, UNKNOWN, reconciliation and trace links | Correlate ledger evidence with the same test run; isolate database lifecycle |

The current Web Agent uses local `FunctionToolset` wrappers. The MCP server is a separate stdio entry point sharing domain services. A passing Agent test does not prove MCP transport works. An in-process `server.call_tool()` test does not prove client/server protocol compatibility.

The current observability extra installs the OpenTelemetry SDK, OTLP/HTTP exporter, FastAPI integration and HTTPX2 integration. Logfire and Pydantic Evals are not required. Existing unittest and JSON evaluation code remain the test framework.

## 2 Observe the pipeline at explicit boundaries

Use a server-generated trace ID for correlation and retain the current run/conversation IDs. A trace ID is never an identity or authorization token. Client-supplied baggage and run IDs must not grant scope.

| Boundary | Record | Why |
|---|---|---|
| ETL extract/transform/validate/load/readback | Batch ID, input hash, mapping version, row counts, quarantine counts, target IDs and reconciliation | Connect a wrong business fact to its original import |
| Web request and Agent admission | Request/run/trace IDs, profile, authentication outcome, queue wait, body size | Separate access failures and waiting from model time |
| Model request | Model/revision/config, request sequence, prompt/schema hashes, duration, tokens, finish/error reason | Identify model, prompt, budget or parser regressions |
| Tool invocation | Tool-call ID, name, validated arguments, start/end, result reference, errors | Identify wrong selection, wrong arguments and failed execution |
| Guardrail check | Policy ID/version, allow/deny/unknown, reason code, relevant facts | Show exactly where execution was allowed or stopped |
| Domain and upstream read | System, operation, object references, scope decision, source version/time, count, duration, partial status | Separate model behavior from data/adapter problems |
| Answer verification | Assertion ID, expected, actual, comparator, evidence reference | Identify an unsupported or contradictory final answer |
| AG-UI/SSE and browser | Event sequence, tool-call linkage, terminal states, disconnect, screenshot/trace references | Separate backend success from streaming/rendering failures |
| Action execution | Action/revision/attempt IDs, approval, lease, preflight, remote result and readback | Explain duplicate prevention and unknown outcomes |

Measure queue delay, model time, tool time, upstream time, first visible output, and total wall time separately. Summing parallel spans is not total latency. Count token usage at model-request level to avoid double-counting parent totals. Missing usage is unknown, not zero.

An illustrative direct Agent trace should read like this:

```text
case CS33 / repeat 1 / trace 8b…
  identity.resolve                     ALLOW
  agent.run
    model.request 1                    tool=get_customer_overview
    tool.call call-01
      input.validate                   PASS
      scope.check                      ALLOW
      domain.customer_overview
        adapter.read                   fixture=mini-trade-v1
      result                           orders=[]
    model.request 2                    answer="There are 100 orders"
  answer.check order_count             FAIL expected=0 actual=100
  evidence.finalize                    COMPLETE
```

This is a proposed example, not an observed trace. In an MCP transport case, add client/server initialize, tools/list and tools/call records. For the current stdio transport, record MCP session and JSON-RPC request IDs in the harness. Link them to tool spans; do not add trace fields to business tool arguments. Propagate trace metadata only through a mechanism both SDK ends support. Until that exists, show linked client/server evidence rather than claiming a fully propagated distributed trace.

## 3 Tracing setup

Use OpenTelemetry for spans and an ordinary local evidence directory for reproducible test results. The implemented viewer path is Collector → Langfuse; a local OTel viewer is an optional development alternative. The viewer is replaceable; it should not own the only copy of test evidence. Pydantic AI supports OTel without Logfire. [Pydantic AI instrumentation](https://pydantic.dev/docs/ai/integrations/logfire/) · [OTel trace concepts](https://opentelemetry.io/docs/concepts/signals/traces/)

The dependency setup is implemented; install the extra with:

```bash
uv sync --extra observability
```

Resolve compatible versions and commit the lockfile. Configure one tracer provider per process before constructing Agents. The installed API supports `Agent.instrument_all(InstrumentationSettings(...))`, including `tracer_provider` and `include_content`.

The current bootstrap is in `src/operion_etl/observability.py`. The following snippet illustrates its provider setup:

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings


def configure_observation(service_name, local_trace_endpoint):
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=local_trace_endpoint))
    )
    trace.set_tracer_provider(provider)
    Agent.instrument_all(
        InstrumentationSettings(
            tracer_provider=provider,
            include_content=False,
            include_binary_content=False,
        )
    )
    return provider
```

The endpoint must be the configured trace ingestion URL, not a viewer page. Application startup and shutdown now initialize and flush the provider when `OPERION_OTEL_ENABLED=1`. The Collector is configured separately as described in the operating runbook.

Add custom spans around guards, domain operations, adapters and answer assertions. Instrument HTTP boundaries only with an integration compatible with this repository's `httpx2`, or create spans explicitly around adapter methods. Do not assume an `httpx` integration captures `httpx2` calls.

For complete public/synthetic fixtures, explicitly enable sanitized message/argument/result evidence in the local test recorder. For private/live data, default to metadata and allowlisted redacted fields. Never capture Authorization/Cookie headers, passwords, API keys or connection strings. Hashes identify artifacts but do not anonymize sensitive values. Capture externally observable requests, responses and decisions, not hidden reasoning.

Use start/end events written incrementally. Ended OTel spans alone can miss a process killed mid-call. A durable test event log should preserve the last start; on recovery classify an unfinished invocation as interrupted/unknown. Telemetry is diagnostic, while the existing action ledger remains authoritative for approvals and side effects. A viewer outage must not create permission to execute an action.

## 4 Guardrails as executable rules

Guardrails belong at the server/domain/action boundary. Prompt wording and MCP read-only annotations do not enforce authorization.

| Proposed rule | Enforcement point | Positive and negative test |
|---|---|---|
| GR01 identity and role | API admission | Valid role succeeds; missing/expired/forged identity fails before model invocation |
| GR02 tool allowlist and schema | Tool dispatcher | Allowed typed call succeeds; forced forbidden tool or injected scope field cannot execute |
| GR03 current object scope | Domain service before returning data | Current allowed relation succeeds; customer/supplier/company reassignment is denied or unverifiable |
| GR04 source integrity | Adapter/domain service | Complete source succeeds; timeout, duplicate key and partial response stay distinct from zero results |
| GR05 freshness and mode | Domain result and answer contract | Snapshot is explicit; stale/unknown delivery cannot become a live delivery promise |
| GR06 budget | Run, model, tool and queue admission | Within-budget call completes; excess calls/time/tokens terminate predictably |
| GR07 output facts | Structured response validation and rendering | Zero remains zero; currency/UOM/status/evidence contradictions fail |
| GR08 controlled effects | Action API and worker | Approved unchanged revision executes; self-approval, old revision and failed preflight cannot send |
| GR09 session isolation | Conversation APIs | Owner can resume; other owner and revoked session cannot read history |

Persist one decision event for each applicable guard: check ID, outcome, reason code, policy version and evidence references. If a guard did not run because an earlier step stopped execution, record NOT_REACHED, not PASS. If observation is missing, report UNKNOWN.

Force negative calls through test doubles, direct tools, MCP and HTTP as applicable. A polite LLM refusal is not proof that the server would block the same request. For identity/allowlist denial, assert zero model/tool/upstream activity where appropriate. For current-relation checks, a minimal upstream read may be necessary: assert no unauthorized data in the returned answer and zero writes, rather than incorrectly requiring zero reads.

For injection cases, put hostile content in the actual fixture note/tool response, not just in the user's question. Assert that it cannot change role/scope, select a forbidden tool, or cause an effect. Maintain legitimate task success cases alongside refusal tests.

## 5 The golden dataset

A golden case is a versioned specification of input, authorized identity, fixture state and expected behavior. It is not merely a question paired with one preferred paragraph.

Create a self-contained synthetic dataset with allowed and forbidden customers, ambiguous names, zero-order customers, complete and partial orders, supplier relations, stale records and controlled faults. Keep it separate from WWI. Start with the existing 15 E2 scenarios, the three reproduced defects, and the minimum transport/protocol cases; expand to CS01–CS40 without claiming the new set has passed.

Each case needs:

- Stable ID, purpose and applicable layers; supported transport and profile.
- Fixture version/hash, mapping version, fixed clock and initial database state.
- Principal reference and server policy version; no tokens stored in cases.
- Prompt or direct tool call, permitted capabilities and prohibited effects.
- Fault injection and cleanup/reconciliation instructions.
- Independent expected facts, acceptable tool paths, guard decisions and source requirements.
- Scorer version and numerical comparators, including money as decimal strings.

Proposed schema example; these fields are not supported by the current E2 runner:

```json
{
  "case_id": "G-ZERO-ORDERS",
  "fixture": "mini-trade-v1",
  "clock": "2026-10-01T09:00:00Z",
  "principal": "sales-a",
  "question": "How many sales orders does customer A have?",
  "layers": ["domain", "mcp", "agent", "web"],
  "expect": {
    "facts": {"customer_id": "demo:customer:A", "order_count": 0},
    "required_scope": "authorized_customer",
    "data_mode": "snapshot",
    "forbidden_effects": ["business_write"],
    "answer_claims": [
      {"entity_id": "demo:customer:A", "field": "order_count", "value": 0}
    ]
  }
}
```

Each layer maps its existing output envelope into comparable facts. Do not compare transport-specific wrappers byte for byte. Normalize only irrelevant differences such as trace IDs; never normalize away ownership, currency, source freshness or an error.

For tool selection, permit business-equivalent routes. Exact sequence assertions are appropriate for protocol requirements or mandatory prerequisites, not every harmless model choice. Enforce that evidence is obtained before making the associated factual claim.

For final answers, validate critical claims against the independently authored gold and against the cited tool evidence. The current `output_type=str` has no claim contract: either add a typed answer/claim representation, or render critical facts deterministically and constrain the narrative. A separate valid claims object does not prove free prose agrees with it. Test rendered text for contradictions too, and treat unconstrained prose checks as limited evidence.

Do not require one exact natural-language paragraph. Use deterministic checks for IDs, numbers, units, statuses, evidence and actions. An LLM judge can supplement clarity/relevance scoring, but cannot be the sole authorization or numerical correctness gate.

Maintain scorer tests that deliberately give it incorrect answers. The previously reproduced example—correct zero-order tool data plus a final claim of 100 orders—must fail the scorer. Also test valid paraphrases and negation.

Version gold changes like code: review changes to expected values, record their source, and do not auto-accept current model output as the baseline. Reserve at least 10 CS cases for holdout; replace cases used for tuning. Run real-model cases at least three times, keeping all failures. Fixed settings improve comparability but do not guarantee deterministic model output.

## 6 A simple layered runner

The current entry point is `scripts/verify.sh {setup|offline|web|postgres}`. The following layered interface remains a proposal:

```bash
operion-check doctor
operion-check run --suite smoke --layer domain
operion-check run --case G-ZERO-ORDERS --layer mcp
operion-check run --suite core --layer agent --repeat 3
operion-check run --suite browser --layer web
operion-check run --suite actions --isolated-db
operion-check inspect <run-id>
operion-check replay <run-id> --mode adapters
operion-check compare <baseline-run> <candidate-run>
```

`doctor` should check locked dependencies, fixture checksums, selected profile, data mode, ports, model reachability when needed and disposable-database identity. It must not print secrets, start a write worker or silently switch an existing demo profile.

| Layer | Real dependency | Isolated or fake dependency | What passing proves |
|---|---|---|---|
| domain | Domain service and policies | Self-contained fixtures/adapters | Business and permission logic |
| mcp | Spawned stdio process plus MCP client | Same fixtures | Handshake, discovery, schema, request/result serialization and tool behavior |
| agent fake | Agent orchestration and tools | Scripted `FunctionModel` | Dispatch, errors and guard enforcement under forced model behavior |
| agent real | SGLang and production Agent code | Frozen business fixtures | Model selection, arguments and answers against stable facts |
| integration | Actual read-only ERP/CRM adapters | Model optional | Installed API compatibility and real data relations |
| web | Browser, Next.js, API, selected model mode | Fixture or declared live profile | User-visible completion, streaming, sessions and recovery |
| actions | PostgreSQL and worker | Persistent remote-effect stub, or separate approved isolation environment | Approval, concurrency, idempotency and recovery |

Run the small domain/contract/fake-model suite during editing. Run MCP and disposable database checks on each PR. Run real-model core cases and browser smoke before merging changes to prompts, schemas or streaming. Use the full repeated suite, read-only integrations and recovery tests for releases. A scheduled run is optional; this document does not create one.

Distinguish PASS, FAIL, ERROR, SKIPPED and BLOCKED. Missing model/fixture/database is not a product assertion failure or a pass. A release suite with a required skipped/blocked layer exits nonzero. Keep expected refusal separate from failure: execution outcome DENIED can be test verdict PASS.

Replay has two explicit modes: recorded model responses test orchestration; recorded adapter responses plus the real model test model behavior against fixed facts. Neither proves current live-system correctness. Never replay writes into an ordinary business environment.

## 7 Evidence from every run

Proposed local layout:

```text
reports/dev/<run-id>/
  manifest.json             code/dirty diff, dependencies, model, policies, fixtures
  summary.json              verdicts, required layers, failures, timings
  events.jsonl              start/end/decision/protocol lifecycle records
  assertions.json           expected vs actual with evidence references
  model-messages.json       synthetic or redacted observable requests/responses
  tool-results.json         validated args and authorized outputs
  mcp-transcript.jsonl      transport/session/request records when applicable
  agui-events.jsonl         client-visible event sequence when applicable
  index.html                readable case list, timeline and differences
  junit.xml                 CI result integration
  artifacts/                browser trace/screenshots and sanitized source records
```

The manifest should include commit, dirty-diff digest, Python/Node and package lock hashes, model revision/quantization/parser settings, prompt/tool schema/policy/scorer versions, fixture hash, fixed clock, transport, data mode and whether each dependency was real. Preserve the exact sanitized inputs behind the hashes; a hash alone cannot reproduce a run.

Each assertion needs a structured location, comparator, expected and actual values, evidence pointer and verdict. Example:

```text
case: G-ZERO-ORDERS
assertion: final.order_count
expected: 0
actual: 100
evidence: tool-results.json#/calls/call-01/result/data/orders
execution: COMPLETED
test verdict: FAIL
classification: FINAL_FACT_MISMATCH
rerun: operion-check run --case G-ZERO-ORDERS --layer agent
```

This is illustrative. The report should also show whether the input/tool facts were correct, so the developer immediately knows to investigate final-answer generation/scoring rather than an ERP API call.

The HTML report needs only a filterable case list, timeline, input/output panels, guardrail decisions, expected/actual differences and a rerun command. Begin with a generated static report; a permanent admin application is unnecessary for the first milestone.

Write evidence during execution, finalize reports on success/error/cancel, and preserve unfinished events after crashes. Escape all model/tool content in HTML; never execute returned HTML. Large payloads should be bounded with a full artifact reference and explicit truncation flag. Restrict private evidence access and retention consistently with existing E5 policy; export only reviewed redacted evidence for interviews.

## 8 Commands available today

Run from the repository root. Start with `scripts/verify.sh case` for the implemented minimal report, or `scripts/verify.sh case mcp --layer mcp` for actual stdio transport. The individual entry points below remain available; the full proposed content timeline is not yet implemented.

### 8.1 Domain and in process MCP tests

```bash
PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -p 'test_read_tools.py' -v

PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -p 'test_mcp_server.py' -v

PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -p 'test_agent_runtime.py' -v
```

The tests now use tracked, self-contained fixtures. On 2026-10-11 the full suite also passed from a copy containing only tracked files, using the existing virtual environment (180 passed, 24 database tests skipped). The Agent runtime tests use scripted `FunctionModel`; they do not call the real LLM.

### 8.2 Interactive MCP protocol debugging

Use the official MCP Inspector with the existing stdio command. The following starts with no target; configure the child process explicitly in the UI. For repeatable automation, pin a verified Inspector version after compatibility testing. [MCP Inspector](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector)

```bash
npx @modelcontextprotocol/inspector
```

Choose stdio and command `/home/bo/projects/python/operion/.venv/bin/operion-mcp`. Configure these child environment values in the Inspector, using absolute paths:

```text
OPERION_CANONICAL_DIR=/home/bo/projects/python/operion/data/canonical/interview-wwi-v1
OPERION_IDENTITY_MAP=/home/bo/projects/python/operion/reports/interview-wwi-v1/identity_map.csv
OPERION_DATA_MODE=snapshot
OPERION_OBSERVED_AT=2026-10-07T00:00:00Z
OPERION_COMPANY=AI Demo GmbH
OPERION_CUSTOMER_IDS=wwi:organization:customer:65
OPERION_SUPPLIER_IDS=wwi:organization:supplier:7
```

The observation timestamp above is a fixed test input, not a claim about when WWI was updated. It may intentionally produce stale-data warnings; retain the dataset source timestamp. Snapshot startup requires this field. For automated freshness tests, inject a fixed clock and explicit fresh/stale timestamps.

No model is needed for these MCP calls. Inspect tools/list and call `get_customer_overview` with `{"customer":"wwi:organization:customer:65","max_orders":20}`. Repeat with an out-of-scope customer and malformed arguments. Capture the response/error and confirm only authorized facts appear. Logging must go to stderr or a file; stdout belongs to the MCP protocol. This Inspector session was not run during preparation of this guide.

### 8.3 Real model and Web checks

For the existing E2 golden set, use its own prepared E2 canonical directory and reconciled identity map. Do not substitute the WWI fixture: expected identities and counts differ.

```bash
.venv/bin/operion-evaluate-e2 \
  --cases evaluations/e2/cases.json \
  --canonical-directory "$OPERION_CANONICAL_DIR" \
  --identity-map "$OPERION_IDENTITY_MAP" \
  --observed-at "$OPERION_OBSERVED_AT" \
  --output reports/dev/e2-current.json
```

Requires the E2 environment and SGLang described in [the E2 runbook](../../ops/e2-agent.md). This command produces current-format tool/answer evidence, but its current scorer can miss final-fact errors. Use a distinct output path for every retained run.

For an already-running WWI Web profile:

```bash
.venv/bin/python scripts/verify-interview-complex-cases.py \
  --base-url http://127.0.0.1:3100
```

This executes five real Web/API/Agent/tool cases and checks SSE order and answer markers. It does not click a browser or prove full semantic accuracy. The existing script outputs summaries rather than complete transcripts; capturing normalized events and final answers is part of the proposed enhancement.

### 8.4 Action tests

The action-control tests execute `DROP SCHEMA public CASCADE` only after the Docker runner issues an in-process ownership capability. Run `scripts/verify.sh postgres`; a supplied DSN is ignored, and direct destructive-test execution without ownership is rejected before connecting. Docker must be available.

After that isolated setup, `operion-evaluate-e3` provides structured W01–W15 evidence. Keep its database URL in environment configuration and the report free of credentials. The current evaluation is an action-control test with a persistent stub; real Twenty effect testing remains a separate isolated stage.

## 9 Implementation order and completion criteria

| Step | Scope | Completion evidence |
|---|---|---|
| 1 | Self-contained fixtures, golden schema, shared case ID and report envelope | One case runs from a clean checkout; bad expected result gives nonzero exit |
| 2 | Local incremental recorder, guard events, spans and model instrumentation | Same trace links model/tool/guard events; exception and interruption leave evidence |
| 3 | Domain, real stdio MCP and scripted-model runners | Same case yields equivalent facts; handshake/schema failures are visible |
| 4 | Real-model final-fact scoring and scorer tests | Correct tool plus incorrect answer fails; valid paraphrase succeeds |
| 5 | HTML/JUnit, per-case rerun and comparisons | A developer can identify failing layer and replay without reading unrelated logs |
| 6 | Web transcripts/browser checks and disposable action database | Streaming/session failures and UNKNOWN recovery are visible in the same report |

Start with one happy path, one scope denial, one upstream outage, one wrong final answer and one interrupted call. Expand after the report makes those five cases easy to explain. Steps 1–5 are a focused slice of the existing roadmap, not extra work to count twice in its estimates.

Acceptance requires: a clean-checkout smoke run; real MCP transport evidence; forced guardrail rejection; correct final-fact scoring; distinct blocked/skip reporting; evidence surviving a simulated interruption; no secrets in reports; and an independently reproducible failure followed by a passing fix. Actual write safety continues to rely on the action contract and its dedicated tests.
