# E2 Agent API v1

This contract defines the local, read-only Agent boundary used by the E2 demo.

## Authentication and authority

- Every `/api/*` request requires `Authorization: Bearer <OPERION_AGENT_TOKEN>`.
- The browser never receives that token. Next.js forwards requests server-side.
- `threadId`, `runId`, client history, advertised tools, state, and context are
  untrusted input. IDs are syntax checked; run IDs cannot be replayed.
- The Python service binds a conversation to its server-configured user, loads
  history from SQLite, and replaces client history with only the latest user
  prompt.
- The only executable business tools are `get_customer_overview` and
  `check_fulfillment`; the per-run allowlist is resolved on the server.

E2 is a single-user local demo boundary. A multi-user deployment must replace
the fixed service identity with authenticated per-user identity and tenant
claims before exposing the Next.js proxy publicly.

## Endpoints

### `POST /api/agent`

Accepts an AG-UI `RunAgentInput` JSON body and returns AG-UI events as
`text/event-stream`. The service enforces request size, prompt size, model/tool
budgets, one active run per conversation, a global concurrency limit, and a run
timeout. Client disconnects cancel the run and release its slots.

### `GET /api/conversations/{conversation_id}`

Returns a browser-safe AG-UI message list rebuilt from trusted server history.
It contains user text, assistant text, tool calls, and tool results, but not
system prompts, hidden reasoning, credentials, or model-internal messages.

### `POST /api/runs/{run_id}/cancel`

Requests cancellation of an active run owned by the authenticated service
identity. Completed runs return their stored status and unknown runs return 404.

### `GET /health`

Returns mode, model name, and the exact two-tool list. It contains no secret or
upstream credential.

## Failure contract

HTTP validation and authorization failures use 4xx status codes. Once an SSE
run starts, model, tool, limit, and timeout failures are emitted as AG-UI
`RUN_ERROR`; they are never rewritten as success. Tool-domain errors use stable
codes such as `ambiguous_customer`, `scope_denied`, `source_unavailable`, and
`invalid_business_input`.

The SGLang compatibility adapter changes only a non-stream response metadata
field (`metadata.weight_versions`) from an array to its JSON-string form. It
does not alter messages, tool calls, stream chunks, status codes, or retries;
transport retries are disabled.
