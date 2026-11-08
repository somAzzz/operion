# Frontend plan: assistant-ui and AG-UI

Version: v1.6; documentation reconciled 2026-11-08. E2–E4 UI and server-side enterprise token forwarding are implemented. Local Keycloak/HTTPS protocol controls and bounded navigation/session browser checks exist. Full actual-user/browser/operations acceptance remains pending; see the [current queue](improvement-plan.md).

## 1. Technology and scope

Use **assistant-ui + shadcn/ui**, starting from the official `with-ag-ui` template without forking a full chat platform. AG-UI connects to FastAPI/Pydantic AI; authenticated REST connects to the action service. Neither transport supplies authorization facts for the other.

```text
Operion Web (Next.js, assistant-ui, shadcn/ui)
  |-- AG-UI/SSE --> FastAPI / Pydantic AI --> shared scoped read services
  |                    |                     optional proposal capability
  |                    +--> AnswerPlan / EvidenceRegistry --> server-rendered answer
  +-- REST ------> Action Service / PostgreSQL --> independent write Worker
                         proposal, revision, approval, execution, events
```

Current application code lives in `apps/web/`. The original planned `/chat` route was implemented at `/`; workspace route groups do not change public URLs.

| Route | Purpose | Current scope |
| --- | --- | --- |
| `/` | Evidence desk and conversation | Thread, verified answer, tool evidence, source/missing-data cards, history |
| `/approvals` | Review pending actions | Server preview, approve/reject, expiry/conflict |
| `/actions`, `/actions/:id` | Execution facts | State, events, readback, target link, manual-review guidance |
| `/session` | Session controls | Same-origin POST sign-out |
| `/login` | Expired/missing-session landing | Public GET/HEAD, no chat runtime or history request |

`Agent.to_web()` is a development diagnostic, not the production UI or an authorization boundary. Do not add CopilotKit, Chainlit, Appsmith, or a second chat-state framework without a demonstrated gap and separate review.

## 2. Authoritative state and trust

- The browser never connects directly to SGLang, holds business-write credentials, or invokes arbitrary HTTP/GraphQL/SQL/Shell.
- Identity, tenant, company, and scope come from verified server policy. Browser roles, `approved_by`, ownership, and permission claims are untrusted.
- Treat AG-UI messages, results, state, and history as client-controlled. The server loads trusted history; replaying calls, approval text, or old messages grants nothing.
- Client tools perform navigation, copy, collapse, and display only. Server tools perform business reads/proposals; only an independently approved deterministic Worker writes.
- Interrupt/resume does not replace action/revision/approval tables. Approval requests reference `action_id`, `revision`, `decision`, and an idempotent `request_id`; payload remains server-owned.
- Action Service is authoritative for `PENDING_APPROVAL`, `APPROVED`, `EXECUTING`, `SUCCEEDED`, `CONFLICT`, and `UNKNOWN/RECONCILING`. Chat/browser state cannot declare success.
- Default operation does not require external conversation storage. Review location, access, retention, and deletion before adding Assistant Cloud or another persistence/telemetry service.

Cookie sessions require CSRF protection. Tabs, refresh, and relogin reload action state from the server. Cache only recoverable display data, never execution eligibility.

Navigation uses verified current roles and hides unavailable links without replacing route/API/backend checks. Action links disable prefetch. See [navigation access](navigation-access.md). The private deployment/network boundary remains mandatory.

## 3. Components and result presentation

Extend assistant-ui Thread, Composer, and message components with business result cards:

| Component | Display | Prohibited behavior |
| --- | --- | --- |
| `CustomerOverviewCard` | Identity, sources, record links, times, missing fields | Automatic same-name merge |
| `FulfillmentResultCard` | Rule version, quantity/unit, warehouse, check time, unknown reason | Delivery guarantee from a rule check |
| `ActionProposalCard` | Action/revision, target, parameters, effects, expiry | Client reconstruction/modification of executable payload |
| `ActionStatusCard` | Current state, attempt/readback, target link, next step | Timeout/unknown shown as success or confirmed failure |

Proposal cards may link to independent review on `/approvals`. Mobile users must be able to read target, revision, deadline, and effects without hover.

Business answers use [structured evidence](structured-answer-evidence.md). The model chooses current evidence references; the server validates and renders the final text before publication. Do not stream unverified model business text, expose output-tool arguments, or provide a free-form prose fallback. Tool progress is separate from first verified answer latency. The transport may remain SSE without token-by-token business prose.

Hide model thinking. Show redacted, understandable tool progress. Auth headers, internal prompts, raw exceptions, private fields, and credentials never belong in browser logs/errors. Ambiguous single-object requests show server-backed candidates; the backend owns selection state and blocks illegal continued calls.

## 4. Interface boundaries

### AG-UI conversation channel

- `POST /api/agent` is implemented through the FastAPI AG-UI adapter and same-origin Next.js proxy.
- Resolve actual identity, scope, conversation, and tools before running; do not trust body identity/history.
- Verify tool events, final verified text, cancellation, timeout, disconnect cleanup, upstream errors, and limits. Failed runs cannot appear successful or save an unverified answer.
- Restore threads from server history. Client/local history is presentation state only.
- Handle API 401 with one full navigation to `/login?reason=session_expired`; preserve 403 and network-error semantics, retain conversation identity, and never automatically replay an interrupted POST. See [session expiry](session-expiry-login.md).

### Action REST channel

```text
GET  /api/actions?status=PENDING_APPROVAL
GET  /api/actions/{action_id}
POST /api/actions/{action_id}/decisions
GET  /api/actions/{action_id}/events
```

Decisions contain only server references, revision, decision, idempotent request ID, and optional reason. They cannot replace execution parameters. Duplicate clicks/retries, old revisions, expiry, cross-user/tenant access, and forged identity remain server responsibilities. The [E3 contract](../../contracts/e3-action-control-v1.md) defines final schemas/errors/transitions.

## 5. Implementation and acceptance by stage

| Stage | Implemented scope | Evidence/release limit |
| --- | --- | --- |
| E2 | `apps/web/`, assistant-ui/AG-UI, server history, read-result cards at `/` | Historical fixed read-only baseline; current model/task/browser coverage accepted separately |
| E3 | Stub-backed approval/action pages and REST client | Historical production build, REST integration, server permission checks |
| E4 | Proposal card, exact preview, independent approval, target link after verified success | Isolated Task path only; no general writes |
| E5 | Token forwarding, local OIDC/HTTPS, CSRF, current-role navigation, expiry login/recovery | Technical/bounded checks exist; actual-user matrix, accessibility/responsive completeness, alerts, and ten-day observation remain pending; writes closed |

Pin JavaScript versions/lockfile and test assistant-ui, AG-UI client, and Pydantic AI as one compatibility set. Scaffolding is a creation step, not reproducible deployment. Approval/action pages can evolve with stubs before real effects; real wiring stays gated by E4.

## 6. Acceptance checklist

### Conversation and reads

- Tool progress and verified output, cancellation, timeout, and disconnect release resources; failure is not success.
- Refresh/relogin restores only authorized user/tenant history; forged conversation/call history fails.
- Cards display source, business/fetch time, rules, missing fields, mode, and simulated markers.
- Source failure, duplicate names, and stale data retain distinct service/clarification/unknown presentation.
- Keyboard can send/stop/open details/navigate approvals; status is not color-only.
- Direct illegal calls remain blocked despite a model bypassing the visible candidate-selection interaction.

### Approval and actions

- Refresh, closed chat, or another device cannot lose or mutate pending server actions.
- Old/expired/cross-user decisions, replaced parameters, and missing CSRF cannot write.
- Duplicate approval/retry creates no second execution qualification or effect.
- `UNKNOWN/RECONCILING` requests waiting/reconciliation/manual review, never a “create again” shortcut.
- Displayed target, parameters, effects, revision, and executor payload correspond through digest/audit evidence.

UI checks supplement, not replace, E2 C/F/P/A and E3/E4 W01–W15 server tests. Both evidence sets are needed.

## 7. Non-goals and change rules

Do not build a generic Agent platform, multi-agent orchestrator, visual workflow editor, plugin marketplace, or multichannel support system in the first scope. UI components are not business authorization. New pages, client business tools, external history, another chat framework, or direct browser/model access need business value, data boundaries, and acceptance cases before inclusion.

## 8. Official references

- [assistant-ui AG-UI Quickstart](https://www.assistant-ui.com/docs/runtimes/ag-ui/quickstart)
- [assistant-ui AG-UI Overview](https://www.assistant-ui.com/docs/runtimes/ag-ui/overview)
- [assistant-ui Runtime Options](https://www.assistant-ui.com/docs/runtimes/ag-ui/runtime-options)
- [Pydantic AI AG-UI](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/)
- [Pydantic AI Web UI](https://pydantic.dev/docs/ai/guides/web/)
- [shadcn/ui](https://ui.shadcn.com/docs)
