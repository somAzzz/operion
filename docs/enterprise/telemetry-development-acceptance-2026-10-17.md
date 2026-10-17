# Development telemetry acceptance — 2026-10-17

Status: **PROTOCOL_AND_CLOUD_VERIFIED / BROWSER_PENDING_CA_RELOAD**.

The authenticated Web → Agent → Collector → Langfuse path was tested before and after the change using the local synthetic Alice identity and the public Wide World Importers snapshot (`interview-wwi-v1`, customer 65). The protocol client verifies the local CA and hostname and completes the existing OIDC code/PKCE flow. No business object was written. Protocol requests create local conversation/run history and Langfuse observations.

## Applied configuration

The running Web and Agent use release `dev-20261017-45c846b-e05340c7fe`, telemetry environment `development`, and `OPERION_OTEL_INCLUDE_CONTENT=1`. These values are persisted in the ignored `.env.langfuse.local`; deployment must explicitly use that env file. Authentication mode remains `OPERION_ENVIRONMENT=enterprise`. The build identifier includes the Git baseline and a fingerprint of the edited runtime files, since the workspace contains pre-existing uncommitted changes.

Prompts, model responses, model parameters, tool arguments/results, and the business run input/verified output are now captured. Binary content remains disabled. The content switch defaults to off outside the explicitly configured development stack. Historical traces are not backfilled.

## Before / after evidence

| Check | Before | After |
| --- | --- | --- |
| Authenticated request | HTTP 200, succeeded | HTTP 200, succeeded |
| Observations for comparable customer-overview request | 182 | 15 |
| ASGI send/receive observations | 167 | 0 |
| Generations | 2 | 2 |
| Named TOOL observations | 1 | 1 |
| Web/Agent environment | default / enterprise | development throughout |
| Version | empty / dev | explicit release throughout |
| Prompt/response/tool content | message structure only; no prompt/answer text or tool payload | verified present |
| Parent links | Web → FastAPI → business run → agent/model/tool | same, no missing parents |

- [Baseline trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/a7378c96bc321cd898a2b507a2dc090c)
- [Verified development trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/353e579c4d7805827448da187d4a9c88)
- [Synthetic status mapping trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/916ae51dd1d108e01312cb59c559a5a4)

The baseline model I/O retained message structure and tool definitions despite content capture being disabled; it did not contain the question or answer text. In the new trace, both model requests contain the actual test question, the final generation contains response text, and the TOOL node contains its input/output.

The 15-node trace passed all 11 automated checks in `scripts/verify_langfuse_trace.py`, including tokens, content presence, consistent release/environment and the successful run outcome.

The health route returns HTTP 200 without identity/business data. The normal unauthenticated page still returns 401 inside the private Web service. Across an approximately 85-second complete Langfuse query window with normal business and middleware observations present, there were zero observations containing `/health`. The first probe tried to correlate the unauthenticated page using its incoming trace ID; that ID was not found, so this empty result was not accepted as a positive control. The subsequent bounded environment/time-window query confirmed the ordinary GET/middleware observations and absence of health observations.

Thirteen content-free synthetic outcome observations were exported through the real Collector and read back from Langfuse: technical failures/timeouts/upstream errors were ERROR; expected denial/rejection/blocked output were WARNING; success and cancellation were DEFAULT. Their dedicated `acceptance.*` names exclude them from dashboards filtering on `operion.agent.run`. Offline HTTP/SSE tests additionally verify a real timeout produces an ERROR business run, even though the stream starts with HTTP 200.

## Validation

- Final Python suite: 221 tests, 197 passed, 24 database integration tests skipped; no failures. No database code changed in this work.
- Focused Agent, guardrail and telemetry tests: 31 passed.
- Ruff and `git diff --check`: passed.
- Web TypeScript and production build: passed in the Docker build.
- Rebuilt and recreated only Web/Agent; both became healthy. The existing Langfuse Collector was retained.
- Complete cloud trace checks: 11/11 passed.
- Synthetic cloud status mapping: 13/13 passed.

Local evidence (ignored report directory):

- `reports/enterprise/observability/20261017/baseline.json`
- `reports/enterprise/observability/20261017/optimized.json`
- `reports/enterprise/observability/20261017/verified.json`
- `reports/enterprise/observability/20261017/health-probe.json`
- `reports/enterprise/observability/20261017/health-window.json`
- `reports/enterprise/observability/20261017/status-verification.json`

## Remaining browser check

The in-app browser initially reported `ERR_CERT_AUTHORITY_INVALID`. The user installed the project's development CA into Ubuntu's system trust store successfully. A new in-app tab in the still-running application continued to report the certificate error. Browser rendering/click acceptance is therefore pending an application restart or browser-specific CA trust refresh; it is not represented as passed by the protocol/API evidence above. The certificate is valid until 2026-10-29. TLS validation was never disabled.

For dashboard statistics, count only `operion.agent.run` as a business run, and only TOOL observations as tool calls. Use `metadata.run_status` and `metadata.result` for outcomes. A successful safety refusal is not a correctness failure, and runtime outcomes are not evaluation scores.
