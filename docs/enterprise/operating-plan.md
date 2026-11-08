# Operion enterprise operating plan

Version: v1.2; documentation reconciled 2026-11-08. This plan combines implemented architecture with explicitly labeled operational targets. It is not a claim of production deployment or E5 acceptance. See the [current status/queue](improvement-plan.md) and [architecture decision](../architecture/adr-001-deterministic-agent.md).

## 1. Purpose, status, and boundaries

Operion is a controlled business Agent layer above Twenty and ERPNext. Business systems own authoritative facts; deterministic domain tools read and calculate them; the model understands requests and selects capabilities/evidence; people retain material judgment; the server controls execution and final rendering.

E0 verified minimum WWI ETL, target readback, and experimental recovery; see [E0 results](e0-baseline-result.md). E1 domain reads, E2 Agent, E3 action stub, and E4 one Twenty internal Task path passed their recorded experimental acceptance. E4 is limited to an isolated public/simulated workspace: the Agent proposes without write credentials, and an independent approval permits a Worker to create/read back deterministic Task/TaskTarget IDs. Real-data writes, full actual-user identity acceptance, alerts, and release operations remain gated by E5 and write-specific acceptance. Generic GraphQL capability must not become a model tool.

Current code also includes closed evidence plans/server rendering, server-owned ambiguity selection, cross-turn revalidation, budget diagnostics, local OIDC ingress, and bounded session/navigation browser checks. These implementation facts do not extend old model, live-source, or operational acceptance.

The first business loop is customer overview → frozen fulfillment rules → eligible internal follow-up proposal → exact preview/approval → deterministic creation → readback/audit. Do not promise delivery, infer unknown inventory, or automatically change identity mappings. Current fulfillment cases do not constitute live stock/reservation/delivery evidence.

| Operating level | Data/capability | Gate |
| --- | --- | --- |
| Experiment | Public sample, labeled simulation, isolated systems | E0; only approved preparation writes |
| Read-only demo | Scoped queries and frozen fulfillment | E1/E2; no Agent business-write credentials |
| Controlled-write demo | Internal follow-up Task | E3/E4 and per-action approval |
| Single-user pilot | One actual user/company and defined hours | Applicable E5 actual-user/data controls; initially read-only |
| Expansion | New writes, sync, companies, or industry | Individually accepted E6 scope |

Initial writes exclude quotations, formal orders, invoices, payment, inventory changes, external messages, bulk deletion, and field/permission changes. Later expansion does not inherit authority for them.

## 2. Business ownership and responsibilities

| Domain | Authority | Operion role |
| --- | --- | --- |
| Contacts, follow-up, opportunities, customer segmentation | Twenty | Scoped reads and limited follow-up Task creation |
| Accounting identity, payment terms, items, inventory, transactions | ERPNext | Scoped reads/rules; formal actions stay in the business system |
| Cross-system IDs, mapping versions, batches | Integration layer | Identity linking, provenance, reconciliation |
| Proposals, approval, execution events | Operion action service | Authorization/execution evidence, not a duplicate business master |

Twenty Company is not ERPNext Company. Equal names do not establish identity. Customer handoff/mapping changes require their own business action. Resolve conflicting fields by ownership, not generic last-update-wins.

| Role | Responsibility |
| --- | --- |
| Business owner | Fulfillment rules, Task effects, scope, benefit |
| System/data owner | Accounts, scope, import/reconciliation, target capabilities |
| Developer/maintainer | Contracts, implementation, tests, upgrades, repairs |
| Operator | Deployment, credentials, backup, alerts, incidents, recovery |
| Permission/data-governance owner | Actual-user mapping, sensitive fields, retention, access review |
| Action approver | Exact content/impact; approval does not replace permission |

One operator may implement and self-check a read-only pilot, with their actual name recorded and writes closed. The action service forbids self-approval. A second test account is not an independent approver. Real writes/high-impact expansion need an independent person and separate acceptance.

## 3. Architecture and deployment

```text
Web (Next.js / assistant-ui)               scoped MCP stdio client
  |-- AG-UI --> authenticated Agent API            |
  |               |                               |
  |               +--> shared deterministic read services --> Twenty / ERPNext
  |               +--> SGLang through model transport
  |               +--> AnswerPlan / EvidenceRegistry --> verified server-rendered text
  |               +--> optional eligible proposal ---------+
  +-- REST --> Action API / PostgreSQL <-------------------+
                      |
                trusted preview/approval
                      |
                deterministic Worker --> restricted target write API
                      |
                readback, audit, reconciliation
```

The current Agent calls shared Python domain services directly through `FunctionToolset`. The separate stdio MCP entry point exposes those same services; Web requests do not all traverse network MCP. Enterprise MCP deployment/identity integration is a separate topology that must be verified rather than inferred from the local stdio server.

- Web presents conversation, evidence, and actions without write credentials or trusted client state.
- Ingress obtains validated identity and scope, stripping client identity claims.
- Agent selects allowed reads/evidence and eligible proposals, never executes target writes.
- Domain tools enforce fields, volume, scope, provenance, time, resolution, and deterministic calculation; Agent/MCP share rules.
- Evidence validation binds run/scope/entity/field and renders facts. No free-form business prose bypass is allowed.
- Action Service normalizes/validates immutable revisions and owns previews/approval.
- Worker supports fixed actions, rechecks current eligibility, leases work, and executes persisted content exactly.
- Adapters own supported API pagination, timeout, types, and error normalization; no arbitrary model-specified requests.

AG-UI carries tool progress and verified final text; REST carries action review/state/events. `Agent.to_web()` is diagnostic only. UI interrupts/history cannot replace server conversations, immutable revisions, or approval. See the [frontend plan](frontend-plan.md).

Keep the modular repository application; do not build a generic Agent platform. One process serves the read-only phase. Agent and write executor use separate processes/identities; only the executor receives the write key. A colocated Worker is not host isolation or high availability.

Separate development, acceptance, and enterprise data/databases/credentials/model logs/backups. Only trusted ingress is user-reachable. SGLang, action database, and executor are private. Authenticate services, encrypt cross-host transport, and prove network isolation in the actual topology.

### Twenty built-in AI and bypass prevention

Keep built-in AI actually read-only or disable its relevant entry points. The model proxy is not a permission boundary. Inventory native tools/MCP/plugins/workflows and Operion paths; verify all Agent writes are controlled. Human business-system users retain their own supported workflows.

If the deployed version cannot constrain built-in AI, disable the capability. Prompts/output filtering cannot substitute. ETL, admin, read tools, and Worker use separate credentials; never delegate admin authority to the model.

## 4. Model transport and optional proxy

Model revision, tokenizer/chat template, SGLang, tool parser, Pydantic AI, and runtime settings form one compatibility baseline. Record exact repositories/revisions/checksums, not only a model size/name.

Use one Agent; the deterministic executor is not another LLM. Thinking is a measured quality/performance option, not a safety guarantee.

Add a proxy only for demonstrated parameter, multi-client policy, or protocol diagnostic needs. It must preserve streaming/non-streaming, fragmented tool arguments, cancellation/timeouts, errors, connections, limits, and redaction. Do not silently repair dangerous tool calls. Model transport retries and business-effect retries have separate semantics.

Current defaults are eight model requests, six business tool calls, and a 60-second run deadline. `present_answer` is an output tool, excluded from the business-call count. Settings require at least `max_tool_calls + 2` model requests for final output and one repair. This replaces the obsolete 8-model/12-tool/120-second proposal, which is incompatible with current validation. Profiles may override deadlines/tokens; consult their configuration and the [Agent API](../../contracts/e2-agent-api-v1.md). Read list inputs have a maximum of fifty; completeness, total counts, and aggregates follow their specific [read contracts](../../contracts/e1-read-tools-v1.md), not an arbitrary universal row count.

Exhaustion emits `RUN_ERROR / LIMIT_EXCEEDED`, never success with an unverified partial answer. Previously emitted authorized tool progress remains separate from final-answer publication. Internal content-free diagnostics preserve observed usage, limits, and exceeded dimension; they are not added to public SSE/history. Capacity/concurrency/queue targets still require measurement.

## 5. Identity, authorization, and data protection

Effective authority is user permission ∩ task scope ∩ tool contract ∩ business-state constraints. Model `intent`, `reason`, and `required_capabilities` are suggestions, never grants.

Dynamic filtering reduces exposure; every execution still checks allowlist, ownership, fields, volume, and domain rules. Search, details, relations, aggregates, links, and errors all obey scope. Ambiguous single-object requests create explicit selection state. Subsequent calls, including calls already submitted in the same turn, are checked at execution; cross-turn choices revalidate candidate/conversation/query/current permission. List requests do not force selection; incomplete pages cannot prove uniqueness.

Enterprise identity uses trusted OIDC and server mappings. Verify each MCP deployment's identity/audience/scope path too. Permission changes/session revocation invalidate old authority. Shared service credentials must be narrowed to the requester's scope and their limitations recorded; no shared admin default.

Client history/approval flags are not authoritative. Bind conversations, messages, results, and caches to user/tenant; prevent model-log/history cross-use. Customer notes, pages, and tool text are untrusted data. No arbitrary URL/HTTP/SQL/Shell tools.

Use explicit input fields and `extra='forbid'` on outer/nested models; validate types according to the JSON contract instead of relying on coercion. Distinguish absent from explicit null, reject empty changes/invalid owners/cross-company references/protected fields, and minimize sensitive data sent to the model.

### Operation type and risk

CRUD describes an operation, not risk. Fixed server policy evaluates field sensitivity, volume, money, external effects, reversibility, and user scope. New actions default to denial.

| Capability | Default |
| --- | --- |
| Authorized queries | Automatic within field/volume limits |
| Follow-up proposal | May persist a proposal, not a target Task |
| Follow-up execution | Exact approval, preflight, idempotency, readback |
| Customer updates/other drafts | Separate E6 contract/acceptance |
| External sending, posting, payment, stock changes | Initially human business-system actions |
| Permissions, schema/model changes, arbitrary SQL/Shell, bulk physical deletion | Never business-Agent tools |

## 6. Data, query, and answer contracts

Reuse Canonical contracts/identity maps. Preserve source system, record IDs/links, business and fetch times, rule version, simulation flags, and missing fields. Exact response names follow capability contracts; conceptual `as_of` and `fetched_at` must not be mistaken for a universal implemented schema.

Fulfillment calculations need remaining quantities, UOM, warehouse, reservation ownership, inbound remaining quantities/dates, and shipment/delivery rules. Deterministic services calculate them; unknown support produces insufficient information. Each source exposes its own time. Existing frozen cases are snapshot-only.

Preserve distinctions among not found, forbidden, ambiguous, stale, source unavailable, invalid input, conflict, unknown effect, and limits. The actual public codes/statuses are defined by read/Agent/action contracts; a conceptual taxonomy is not a promise of identical uppercase codes at every API. Failure is not zero inventory; errors must not disclose out-of-scope existence.

Scope caches by user/tenant/permission version/query; keep authorization caches short/revocable. Preflight cannot trust stale cache. Batch reads use stable pagination, bounds, and partial-result markers. Final facts require current-run evidence references; valid schema/support still do not prove the user task is complete.

## 7. Proposal, approval, and execution

### Action object

The server generates `action_id` and immutable `revision`. Generic stub revisions invalidate old approval. E4 target/parameter changes instead require a new proposal from current facts: the generic revision endpoint cannot mutate its protected target. Same-request retries use scoped idempotency; an intentional new Task may have another action ID. Duplicate-candidate UI is a design goal, not a claimed implemented guarantee or global payload-hash merge.

Content includes action/schema type, requester/tenant, business references, normalized parameters, data/permission preconditions, source-backed preview, effects, policy version, creation, and expiry. A model reason is only a claim; retain the user request reference and actual execution facts separately.

Approval binds `action_id + revision + payload_digest`, approver, authentication context, time, expiry, and policy. Normalize target/parameters/scope/preconditions/effects consistently before hashing. Digests do not replace identity/database constraints.

Read preview from the server: system, customer/order, owner, body, deadline, values, and impact. Client decisions cannot resubmit executable parameters. Cookie sessions need CSRF. Approval is auditable/revocable and grants only one revision eligibility.

DeferredToolRequests/Results may pause conversations but are not the action ledger. Recover from persisted server state after restart, not client-assembled history. The executor uses stored parameters; the model selects evidence about the result.

### State machine

Current transitions are defined by the [E3 contract](../../contracts/e3-action-control-v1.md), not by the former illustrative `PROPOSED` diagram:

```text
PENDING_APPROVAL -> APPROVED -> EXECUTING -> SUCCEEDED
       |              |             +-> UNKNOWN -> RECONCILING
       |              |                                |-> SUCCEEDED
       |              |                                |-> APPROVED (proven not submitted)
       |              |                                +-> MANUAL_REVIEW
       |              +-> REVOKED / CONFLICT / CANCELLED
       +-> REJECTED / EXPIRED / CANCELLED
```

Changed policy/permission/preconditions prevent sending and require renewed proposal/approval under the capability contract. A failure response does not prove no effect. Only a demonstrably safe retry retains the same action/attempt evidence and valid approval; never fabricate new approval. A confirmed-no-effect terminal failure and an unknown outcome are different semantics.

Worker transactionally claims approved work with attempt/lease/heartbeat. Lease expiry does not stop a remote request; reconcile before another Worker can resend. Pause/cancel blocks unsent writes; sent requests may succeed and must remain tracked.

Check global/tenant/tool pause at claim and pre-send. Missing authorization, approval, or audit persistence blocks writes. Telemetry can buffer/degrade but cannot lose the authoritative ledger.

## 8. Idempotency, concurrency, and recovery

### Idempotency

Keep `action_id` stable across model/HTTP retries, queue delivery, and restarts; trace/tool-call IDs are not substitutes. Unique constraints and transactional transitions prevent duplicate eligibility; SELECT followed by unconditional INSERT is insufficient.

Prefer native deduplication or a target-enforced unique external action reference with exact lookup. A pre-create lookup alone cannot exclude concurrency. Without reliable deduplication, freeze timed-out writes for manual confirmation instead of promising exactly-once execution.

Local transactions cannot cover remote commits. Timeout, disconnect, or crash after success enters unknown → exact lookup → readback → ledger evidence. If unprovable, escalate manually. Retry needs proof of no submission or reliable target deduplication.

### Concurrency

Existing-record updates/restoration need target-atomic conditional writes, such as a version predicate in the write transaction. An `expected_version` field or gateway lock cannot prevent concurrent human edits in the target. Exclude updates lacking that guarantee. Initial Task creation rechecks related records/owner and states the preflight timing limitation.

### Recovery and compensation

Compensate Task creation through an approved close/cancel workflow; notifications already sent cannot be erased. Field restoration requires version comparison/atomic update; posted records use supported reversals. Compensation is a new independently approved/audited action linked to the original; never rewrite successful history as if nothing happened.

Composite cross-system writes belong to E6 with persistent steps/dependencies, partial success, compensation, and manual intervention. Do not claim cross-system ACID or automatically roll back both systems in the first version.

## 9. Persistence and audit

The implemented PostgreSQL action ledger stores actions, immutable revisions/decisions, attempts, pauses, and append-only events. Preserve user/tenant/request/conversation, action/revision/digest, tool/policy, target, preconditions, approval, idempotency, attempts, remote summary, and readback. Application accounts cannot rewrite history. Independent admin audit/backup/export remains an operational requirement, not proof of tamper-proof storage.

Link results by action ID, conversations by conversation ID, and each execution by trace/span. Approval and later execution can have different linked traces. Traces may be sampled; business audit must not be.

Default logs contain argument summaries, tool, latency, status, versions, and error categories, never secrets/headers. Content capture is explicit and restricted; public/synthetic development opt-in does not authorize private-data telemetry. Initial proposed retention: raw troubleshooting content 24 hours, ordinary diagnostics fourteen days, traces seven days, action/approval events 180 days. Only the applicable implemented session purge is a code guarantee; confirm operational retention/deletion/backup exceptions with data owners before real data. These are not legal requirements.

## 10. Operations, monitoring, and capacity

### Proposed pilot targets

Measure and confirm these before E5; they are not current performance promises. The pilot has one actual user/company and defined hours. Five concurrent sessions are automated load, not five real users; multiple-user expansion needs separate acceptance.

| Metric | Initial target/rule | Measurement |
| --- | --- | --- |
| Ingress/tool availability | 99.5% monthly in agreed hours | Valid requests excluding unauthorized denials; report dependency downtime separately |
| Deterministic reads | p95 ≤ 5 seconds | Fixed scale including upstream reads; cold start separate |
| Complete Agent answer | p95 ≤ 60 seconds | Queue/model included, human clarification wait excluded |
| Approved Task processing | 95% read back within 30 seconds when target healthy | Approval to verified success; unknown separate |
| Unauthorized/unapproved/duplicate effects | Zero tolerance; pause affected writes | Deterministic checks, audit, reconciliation |
| Recovery | RPO ≤ 15 minutes, RTO ≤ 4 hours | Actual recoverable backup and timed restoration |

RPO is the tolerated recent data-loss window; RTO is restoration time. Daily backups alone cannot meet fifteen-minute RPO; use continuous backup/WAL or a verified equivalent. Narrow scope or explicitly revise targets when resources cannot meet them. A single-host homelab is not highly available.

Monitor request success, upstream latency/errors, model queue/tokens, tool denials, approval backlog, unknown age, Worker heartbeat, backup freshness, disk, and connections. Separate read and recovery/write budgets. Existing tracing, verified-text latency, health-noise suppression, and budget snapshots are implemented; capacity/alert delivery still need actual evidence.

Suggested alerts: unauthorized/duplicate effects or audit gaps immediately pause affected writes; unknown over five minutes requires review; five continuous minutes above 5% errors in operating hours or backup beyond RPO alerts the operator. Tune/deduplicate using measured load and record the actual receiving channel. Unattended writes stay paused; do not promise a human response.

Degrade by capability: deterministic reads/action state may remain available without the model; unavailable sources yield partial/unknown results, not fabricated data; absent approval/ledger blocks new writes; failed telemetry cannot hide business state. The UI distinguishes proposal, pending, executing, success, conflict, and unknown.

## 11. Backup, incidents, and release

### Backup and restore

Cover action/needed business databases, attachments, mappings, deployment config, and version manifests. Recover secrets separately. Keep at least one encrypted/access-controlled/expiring backup off the running host. Record each system's restore point; separate backups are not simultaneous.

Disable Worker after restore; reconcile potentially committed remote actions since backup by action ID, rebuild evidence, and do not replay old approvals automatically. Restore writes only after permission/pause/reconciliation checks.

### Incidents

1. Pause writes on unauthorized/duplicate effects or unknown-scope corruption; revoke affected credentials when needed.
2. Preserve request/action/readback evidence and identify users/data/in-flight work.
3. Business owner chooses compensation; do not bulk-restore a snapshot over new data.
4. Reproduce in isolation, repair, and add deterministic/model regressions.
5. Operator/business owner release based on evidence, recording cause, impact, and prevention.

Assigned people handle external communication under the actual incident process. A write pause need not stop legitimate reads unless identity/data isolation is also affected.

### Release and change

Pin lockfiles, image digests, migrations, tool/policy/prompt versions, and model revision. Accept in isolation, then read-only shadow mode, then scoped rollout. Shadow mode has no real writes.

Model/SGLang/template/parser changes rerun compatibility/behavior; tool/permission/executor changes rerun deterministic safety/fault checks. Back up and verify migration compatibility/recovery first; code rollback is not automatic database rollback. Keep the last runnable combination; failed release disables new capability or restores verified versions.

## 12. Testing, operating cadence, and cost

Four layers: pure rules/state → business API integration → model behavior → enterprise end-to-end/fault drills. Directly attack execution without the model: forged identity, approval replay, illegal arguments, revocation, concurrency, timeout, and forged evidence. Test legitimate completion as well as denial; finite passes are not a safety proof.

Daily: failed/unknown work, approval backlog, backup. Weekly: fact quality, denials, slow requests, business feedback. Monthly: accounts, secrets, retention, restore evidence. Upgrade: affected regressions. One operator may perform small-scope operations but retains records.

Track GPU/host/storage, backup, request latency/resources, business API use, and maintenance time. Compare manual and Agent task time while recording factual errors, abandonment, and human intervention. A 30% improvement is a proposed business goal, not measured success. Scale from queue/bottleneck measurements, not agent/tool count.

## 13. Decisions and unconfirmed capabilities

E0/E3/E5 must record actual versions, built-in AI restrictions, Task fields/notifications, target deduplication/exact lookup/conditional update support, identity mappings, GPU capacity, network, backup locations, hours/owners, and retention. Each needs evidence, owner, decision, and affected scope. Unconfirmed is not supported.

Where reliable deduplication is absent, allow only an accepted manual-reconciliation path with no automatic unknown retries; block the tool if that limitation is unacceptable. Where atomic conditional update is absent, exclude automatic updates/restoration needing it.

## 14. References and version applicability

These references inform project decisions; pin and test installed versions rather than assuming the latest online documentation applies.

- [Pydantic AI Toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/): dynamic filtering.
- [Pydantic AI Deferred Tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/): approval/external execution/client trust.
- [Pydantic configuration](https://pydantic.dev/docs/validation/latest/api/pydantic/config/): extra fields and validation.
- [SGLang OpenAI-compatible documentation source](https://github.com/sgl-project/sglang/blob/main/docs_new/docs/basic_usage/openai_api_completions.mdx): model transport; verify template support separately.
- [Twenty APIs](https://docs.twenty.com/developers/extend/api): verify installed permission/concurrency behavior.
- [Frappe REST](https://docs.frappe.io/framework/user/en/api/rest): identity/document access; verify ERPNext state semantics separately.

Execution order and release evidence follow the [delivery plan](delivery-plan.md).
