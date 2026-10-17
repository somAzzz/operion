# OpenTelemetry and Langfuse runbook

Status: implemented as an opt-in integration. Tracing is disabled unless `OPERION_OTEL_ENABLED=1` is set. The Agent, action API, worker, and synthetic E2 evaluator export OTLP/HTTP spans. The Next.js server injects W3C trace context into its upstream requests. The Collector has a local debug configuration and a Langfuse v4 configuration.

## Trace boundaries

One request trace can contain Next.js, FastAPI, `operion.agent.run`, Pydantic AI model/tool spans, domain reads, and ERPNext/Twenty upstream spans. The system trace root may be the Next.js request; `operion.agent.run` is the stable business observation. `agent_runs.trace_id` and `agent_runs.span_id` identify that observation. A conversation becomes a Langfuse session through `langfuse.session.id`. The run ID and session ID are validated for format and ownership by Operion and are diagnostic labels, never authentication.

Action approval and worker execution use separate traces. The action table stores the proposal and approval trace/span IDs. A worker execution span links to the approval span (or the proposal when no approval trace is available). The action ledger remains authoritative for approval, remote side effects, UNKNOWN, and reconciliation.

Web `/health` requests are excluded at sampling time (including their child spans). FastAPI excludes `/health` and its low-level ASGI send/receive spans, so SSE chunks do not each become observations. No Collector span filtering is enabled. Langfuse receives the ancestors needed to reconstruct the trace. Add a Langfuse-only filtered pipeline only after inspecting actual parent relationships and preserving a root observation. The debug pipeline is for local acceptance and should not be used as production storage.

## Enable a local Collector

Install Python dependencies with `uv sync --extra observability`. The gateway Agent container installs this extra during its build. Start a local debug Collector:

```sh
docker compose -f deploy/gateway/compose.yaml --profile observability up -d collector
```

For the gateway containers, set `OPERION_OTEL_ENABLED=1` before starting or recreating `web` and `agent`. They send to `http://collector:4318/v1/traces`. For locally running Python processes, set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces` as well. The exporter uses batching; a stopped Collector does not authorize an action or change its state.

The Collector debug configuration prints basic span summaries to its logs. Confirm intake with `docker logs operion-gateway-collector-1`. It does not provide a persistent trace UI.

## Send to Langfuse

Create a Langfuse project and provision its public and secret keys. Set the following **server-side** variables in the Collector environment or deployment secret store, then select `collector-langfuse.yaml`:

- `OPERION_OTEL_COLLECTOR_CONFIG=collector-langfuse.yaml`
- `LANGFUSE_OTLP_ENDPOINT=https://<your-region-or-host>/api/public/otel`
- `LANGFUSE_AUTH=<base64 of public-key:secret-key>`

The exporter sends OTLP/HTTP to `/api/public/otel/v1/traces` and includes `x-langfuse-ingestion-version: 4`. Do not configure the gRPC exporter for Langfuse. Redeploy the Collector to apply these settings. The API key is held by the Collector, not by Web or Agent processes. The gateway Collector is on both the private backend network and a separate telemetry egress network.

If the action API or worker runs outside the gateway Compose stack, point each process to its reachable Collector URL with `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and enable `OPERION_OTEL_ENABLED=1`. Run `operion-action-migrate` before deploying the updated action API or worker; migration `0002_action_trace_links.sql` adds the correlation columns.

## Privacy and data handling

By default, Pydantic AI instrumentation disables prompt/completion content and model request parameter capture. Development/testing can explicitly set `OPERION_OTEL_INCLUDE_CONTENT=1` to capture model prompts/responses, tool arguments/results, model parameters, and the business run input/verified output. Binary content remains disabled. This setting exports content to the configured Langfuse project; use it for the current public WWI sample development stack and turn it off before using private data. The SGLang HTTPX2 client is instrumented individually; the upstream read/write spans record system and outcome without URLs, request/response bodies, headers, or raw exception messages. The Agent stream span always records status and timing; question/answer capture follows the same explicit content switch. Local run history and action evidence retain their existing access and retention controls.

Synthetic E2 experiments additionally export evaluation questions, expected answers and scores independently of the ordinary development content switch. That path requires both CLI flags `--langfuse-experiment --synthetic-data-confirmed`, `OPERION_OTEL_ENABLED=1`, and Langfuse score API credentials (`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`). Do not use those flags with private or live input data. The evaluator sends one trace per case/repeat and publishes a deterministic Boolean `operion_correctness` score to the root observation. Langfuse's Scores API receives Boolean values as numeric `0` or `1`. Local JSON reports remain the primary test evidence. LLM-as-a-judge can supplement prose quality later; scope, order counts, and action safety stay deterministic gates.

## Acceptance

1. Run `scripts/verify.sh offline` and `scripts/verify.sh web`.
2. For action tests, run `scripts/verify.sh postgres` with Docker available. The runner creates a new isolated container, issues a test ownership capability, and removes the container afterward. Existing DSNs are ignored; tests never use an existing demo database.
3. Confirm an Agent request produces a trace containing a FastAPI server span, `operion.agent.run`, model/tool spans, and only content-free attributes. The run record's `trace_id` and `span_id` must match the Agent observation.
4. Confirm the Next.js proxy forwards `traceparent` to FastAPI and that the trace ID remains the same. Check a cancellation and a failed run for terminal status and ended spans.
5. Confirm an approved action's worker span links to the persisted approval span; UNKNOWN and reconciliation must keep their ledger behavior.
6. Confirm a synthetic experiment has one trace per item, input/output only under explicit opt-in, and a score attached to the correct observation. A real Langfuse UI check requires a reachable instance and project keys.

Official references: [Pydantic AI OTel instrumentation](https://pydantic.dev/docs/ai/integrations/logfire/), [Next.js OTel](https://nextjs.org/docs/app/guides/open-telemetry), [Langfuse OTLP endpoint](https://langfuse.com/integrations/native/opentelemetry), [Langfuse experiment spans](https://langfuse.com/integrations/native/opentelemetry/experiments), and [Langfuse Scores API](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk).


## Development telemetry (2026-10-17)

Keep `OPERION_ENVIRONMENT=enterprise`: this selects the authentication mode, not the telemetry environment. Use these separate variables in the ignored `.env.langfuse.local` file:

```dotenv
OPERION_OTEL_ENABLED=1
OPERION_OTEL_COLLECTOR_CONFIG=collector-langfuse.yaml
OPERION_TELEMETRY_ENVIRONMENT=development
OPERION_OTEL_INCLUDE_CONTENT=1
OPERION_RELEASE_ID=<unique-build-id>
```

Keep the existing Langfuse endpoint/credentials in that same file. Both Web and Agent receive the same environment and release. Generate a new release ID for each deployment (commit plus a dirty-tree content fingerprint is appropriate during development). The current acceptance release is recorded in `telemetry-development-acceptance-2026-10-17.md`.

Apply the configuration explicitly; plain Compose without `--env-file` will use its defaults:

```sh
docker compose --env-file .env.langfuse.local -f deploy/gateway/compose.yaml --profile observability up -d collector
docker compose --env-file .env.langfuse.local -f deploy/gateway/compose.yaml up -d --build --no-deps --wait agent web
```

For a dashboard, filter business runs by observation name `operion.agent.run`. PydanticAI also produces an AGENT observation, so counting all AGENT rows double-counts a request. Count tools at `type=TOOL`; `operion.domain.read` is a nested diagnostic span.

| Business result | Langfuse level | OTel status |
| --- | --- | --- |
| succeeded | DEFAULT | OK |
| failed / error / timeout | ERROR | ERROR |
| denied / rejected / blocked | WARNING | UNSET |
| cancelled | DEFAULT | UNSET |

Use `metadata.run_status` for business result breakdowns. Tool observations and their domain child carry `metadata.result`; expected scope/input/not-found errors are WARNING, while upstream/internal errors are ERROR. Guardrails carry `metadata.verdict` and `metadata.reason_code`; denial/unknown is WARNING, not a technical error. These are runtime outcomes, not correctness scores.

Verify a new successful tool-using request with its stored trace ID:

```sh
PYTHONPATH=src .venv/bin/python scripts/verify_langfuse_trace.py   --trace-id <trace-id> --since <ISO-8601-start-time>   --release <unique-build-id> --require-content   --output reports/enterprise/observability/trace-verification.json
```

The verifier paginates Observations API v2 and checks Web/Agent presence, parent links, model/tool nodes, tokens, consistent environment/version, terminal outcome, content, and absence of SSE transport noise. It prints only checks, not content or credentials. The optional JSON report contains fetched content and stays in the ignored local reports directory. An API protocol acceptance is not evidence of browser rendering or clicks.
