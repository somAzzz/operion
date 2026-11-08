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
- The Agent exposes fifteen read-only portfolio, organization, contact,
  sales-order, purchase-order, and fulfillment operations plus a read-only
  `check_operation_capability` tool. The per-run allowlist is resolved on the
  server. Current contact fields follow `contact-overviews-v2`.

E2 is a single-user local demo boundary. E5 adds the required per-user OIDC,
server-side tenant/customer policy and revocation path; enterprise deployments
must use that mode and the trusted ingress described in the E5 contract.

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

Returns mode, model name, and the server-available tool list. It contains no secret or
upstream credential.

## Failure contract

HTTP validation and authorization failures use 4xx status codes. Once an SSE
run starts, model, tool, limit, and timeout failures are emitted as AG-UI
`RUN_ERROR`; they are never rewritten as success. Tool-domain errors use stable
codes such as `ambiguous_customer`, `scope_denied`, `source_unavailable`, and
`invalid_business_input`.

## Answer and evidence boundary

Business answers use `ToolOutput(present_answer)` and a closed `AnswerPlan`.
The model selects only current-run fact/table references and allowed projections;
`EvidenceRegistry` validates run/scope/entity/field/provenance and renders the final
text deterministically. Free-form business prose, custom row values, and old-run
references are not fallback paths. Output-tool arguments and unverified model text
are not published to SSE or successful history. Failed/cancelled runs retain no
new unverified answer. See the [structured answer contract](../docs/enterprise/structured-answer-evidence.md).

Evidence support is distinct from task completion. Routing, correct parameters,
required-fact selection, omissions, and legitimate user-task success still require
independent evaluation. `AnswerPlan.language` accepts only `en`; server-owned
labels, notices, investigation cards, and provenance are rendered in English.
Source values and user statements remain data and are escaped without translation.

## Run budgets and internal diagnostics

The default and gateway/interview profiles allow six business tool calls and
eight model requests per run. Configuration must allow at least
`max_tool_calls + 2` model requests: one final structured answer and one answer
repair after a sequential chain of business calls. `present_answer` is an output
tool and does not consume the business-tool allowance. Earlier schema retries
or other extra model requests can still exhaust the request allowance; token and
deadline limits remain independent. This is not a guarantee of task completion.

Budget failures remain `RUN_ERROR` / `LIMIT_EXCEEDED` publicly. Internally, each
admitted run records a versioned `budget` snapshot with numeric `usage`, configured
`limits`, and an optional `exceeded` object. Its `kind` is `tool_calls`,
`model_requests`, `input_tokens`, `output_tokens`, or `deadline`; `used` and `limit`
record the observed boundary, and `attempted` records the blocked projected count
for tool/model requests. A rejected batch can have zero executed tools and a
nonzero attempted count. The SDK still enforces the limits.

Success, failure and cancellation retain observed request/tool/token usage.
Streaming token observations are retained even if the SDK has not committed the
final response usage; tokens unreported by an interrupted provider are not
estimated. Elapsed time covers execution after admission, excluding queue wait.
Only expiration of the run's timeout scope is diagnosed as `deadline`; an upstream
timeout is not mislabeled as exhaustion of the total run budget. A budget failure
while repairing an answer takes precedence over the preceding guardrail rejection.

Snapshots are stored in the nullable SQLite `agent_runs.budget_json` column and
returned as `budget` by the internal store reader. Existing rows remain null
(unknown historical diagnostics), with an idempotent additive migration. Numeric
usage/limits and the exceeded dimension are also emitted under `operion.budget.*`
trace attributes. Diagnostic payloads contain no prompts, tool arguments, evidence
IDs, raw exceptions or credentials, and are not added to SSE or public history.
Failed or cancelled runs still do not publish or save unverified answers.

## Candidate selection state

For an Agent search intended to resolve one customer or supplier, a complete
multi-match result creates server-owned clarification state. An incomplete page
asks for a narrower query; the current page does not prove that a record is
unique. Explicit list requests can use the search list mode and present the
result table without forcing a single-object choice. If a list-mode search
instead leads to a `needs_details` answer, the server promotes its current
complete candidate set to clarification state; the run must not fail merely
because the model used list mode. Ambiguous overview resolution also creates a
complete candidate set. The server selects the candidate evidence table and
renders the clarification; the model cannot supply candidate rows or arbitrary
clarification references.

Once clarification is required, every later business tool in that run is
blocked at execution, including calls in the same model response. On successful
completion, the candidate IDs, query, relationship, and authorization context
are saved with the conversation. A follow-up may choose exactly one of those
canonical IDs. The server rechecks conversation ownership, current scope, data,
and query before allowing a single overview lookup of that ID. Unknown IDs,
multiple IDs, stale candidates, and changed scope return HTTP 409. A new
question without a candidate ID clears the pending selection and starts a fresh
model context. The lookup result remains subject to the normal evidence and
authorization checks.

The SGLang compatibility adapter changes only a non-stream response metadata
field (`metadata.weight_versions`) from an array to its JSON-string form. It
does not alter messages, tool calls, stream chunks, status codes, or retries;
transport retries are disabled.
