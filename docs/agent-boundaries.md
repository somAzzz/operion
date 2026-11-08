# Agent / MCP boundaries

Status: Shared read services, the Agent, structured evidence output, and controlled action infrastructure are implemented. E0–E4 acceptance remains limited to the historical experimental scopes. E5 operational acceptance is incomplete; real-data writes are not released.

See [ADR-001](architecture/adr-001-deterministic-agent.md), the [operating plan](enterprise/operating-plan.md), and [E3 action control](enterprise/phases/e3-action-control.md). Tool visibility and model intent confer no permission. The only released experimental write remains one internal follow-up Task path.

## Capability levels

| Level | Capability | Rule |
| --- | --- | --- |
| L0 | Explain processes, fields, and guidance | State uncertainty when the applicable version is unknown |
| L1 | Query authorized data | Server limits identity, company, fields, and query volume |
| L2 | Recommendations, change previews, document preparation | Do not write formal business records |
| L3 | Initially create only an internal follow-up Task | Preview and approve each concrete action; verify workflows and notification effects; defer other drafts |
| L4 | Formal submission, posting, payment, inventory adjustment, external sending | Initially performed by people in the business system |
| L5 | Permission/model changes, bulk deletion, arbitrary SQL/Shell | Never expose to the business Agent |

## Tool contracts

Each tool records purpose, input structure, field allowlist, scope, read semantics, maximum volume, provenance, data time, effects, idempotency, approval requirements, and error types.

The original minimum demo exposed customer overview and frozen fulfillment. The current shared MCP service exposes fifteen snapshot read operations, or fourteen in live mode, where frozen fulfillment is unavailable. Customer, supplier, contact, order, and aggregate capabilities reuse the same domain services as the Agent. Tool count is not an acceptance goal. Data-quality capabilities may later explain recorded import failures.

The Agent can expose `propose_followup_task()` only when server policy and release configuration permit it. This records a `PENDING_APPROVAL` proposal, not a business-system Task. Only the independently approved Worker creates the Task under the [E4 contract](../contracts/e4-followup-task-v1.md). MCP remains read-only.

MCP exposes contracts; business rules have one implementation. Read-only adapters precede Agent use, and incremental synchronization is not a prerequisite. Tool annotations are hints; the server enforces permission.

Do not expose generic database operations, arbitrary record updates, or arbitrary network requests. ETL and business tools use deterministic rules. The model does not calculate accounting facts or rewrite mappings. Final business answers use current-run `AnswerPlan` / `EvidenceRegistry` references and server rendering; no free-form business prose bypass is allowed.

Ambiguous single-object queries create server-owned selection state. Execution gates block further business calls, including calls in the same model response. Cross-turn selection revalidates the candidate and scope; incomplete pages require refinement. Explicit list requests retain list semantics. See the [Agent API](../contracts/e2-agent-api-v1.md).

## Write controls

1. Display system, target records, before/after values, amounts/currencies, basis, and impact.
2. Bind approval to requester, exact action content, record version, and expiry.
3. Recheck identity, permission, business state, and approval before execution.
4. Changed data requires a new preview; never reuse old approval for different content.
5. Keep a stable idempotency key. After timeout, query the outcome before retrying.
6. Verify by readback and retain the result and related record links.

## Identity, evidence, and errors

- Separate read/write credentials and keep them server-side. Map users to actual scope; shared administrator credentials cannot replace permission checks.
- External material and customer notes cannot authorize actions.
- Distinguish no data, no permission, stale data, and source failure; errors are not zero results.
- Define inventory/debt metrics and expose each source's observation time when snapshots differ.
- Audit requester, approver, tool, argument summary, changes, and outcome, with appropriate redaction.
- Provide a global write-pause switch. Correct posted documents through supported reversal/correction workflows, not database deletion.

## Required cases

Normal reads, duplicate names, cross-company access, sensitive fields, source-text prompt injection, stale data, source failures, expired approval, data changed after approval, duplicate requests, timeout after successful write, and partial cross-system success.

All tested unauthorized accesses and unapproved writes must be blocked. Passing finite tests does not prove the absence of other risks; add coverage with every new tool or permission.

## Minimum demo and evaluation

Fulfillment returns satisfiable under the defined rules, quantity/date shortfall, or insufficient information, with business date, warehouse, allocation rules, purchase lines, and source time. Do not invent delivery probabilities or replace unknowns with zero. Current F01–F06 are frozen snapshot scenarios, not live delivery evidence.

The original fifteen cases cover domain tools and Agent behavior; the current expansion target is CS01–CS40, including holdouts, rather than the earlier approximate thirty-case target. Judge facts, permissions, and prohibited actions while allowing equivalent tool paths. Write tests precede release of follow-up execution. See the [minimum demo](minimum-demo.md) and [current improvement plan](enterprise/improvement-plan.md).
