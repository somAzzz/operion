# ADR-001: Deterministic business capabilities and a controlled Agent

Date: 2026-10-21

Status: Accepted as the development and review standard. Acceptance of this decision does not itself prove implementation or runtime acceptance of every capability described below.

## Context

Operion already uses domain tools, structured evidence, and server rendering, but the principles were spread across several documents. Prompt-only repairs can leave business correctness or workflow control dependent on the model following natural-language instructions.

Conversation `56d61b99-450e-4568-867f-716cba9fe841` demonstrated this: after a search returned five customers matching the same name fragment, one run rejected clarification with `NOTICE_AFTER_BUSINESS_LOOKUP`; another looked up candidates individually, repeated calls, and exhausted its budget with `LIMIT_EXCEEDED`. The answer contract and ambiguity workflow must work together; asking the model to clarify duplicate names is insufficient.

## Decision

The model understands requests, selects business capabilities, and organizes evidence. Deterministic domain services produce business facts and judgments. The server controls state transitions, authorization, and execution. The evidence contract and renderer constrain the final answer.

| Responsible layer | Required guarantees |
| --- | --- |
| Domain services and typed contracts | Business calculations, entity resolution, state definitions, explicit result types, provenance, and completeness |
| Runtime and execution entry points | Permission checks, explicit states such as awaiting selection, legal transitions, budgets, and execution prerequisites |
| Evidence and presentation | Current valid references, entity/field binding, scope and freshness, deterministic facts and clarification |
| Model and prompt | Request understanding, routing to existing capabilities, evidence selection, and language preference; these still require task evaluation |

Extend existing domain services, contracts, or runtime behavior first. Add a model-visible tool only for an independent business task. Agent and MCP share business rules. A typed capability includes input constraints, output semantics, and execution checks, not just Python annotations or JSON schema.

Prompts and descriptions may improve use, but must not be the sole guarantee of correctness, permission, ambiguity handling, or workflow gates. Do not hide contract gaps behind free-form business prose, permissive validation, or larger budgets. Missing values do not become zero; a page is not a complete result; snapshots are not live state.

## Ambiguity handling example

Single-object resolution distinguishes resolved, needs selection, not found within scope, and source unavailable. `Resolved`, `NeedsSelection`, `NotFound`, and `SourceUnavailable` are illustrative names, not requirements to add tools or classes with those names.

When selection is required, the server owns the candidate set and scope, generates evidence-backed clarification, and blocks details or actions that depend on an unresolved object. Tool filtering is supplementary: execution entry points must also check subsequent calls already submitted in the same turn. Cross-turn selection binds to the original candidates and conversation and rechecks current permission and selection validity.

An incomplete page cannot establish uniqueness. Explicit requests to list or compare matches retain list semantics and do not automatically force single-object selection.

## Acceptance and consequences

- Explain the failure evidence, invariant, and responsible layer before repairing it; add a regression at that layer. Critical guarantees must survive incorrect model calls or output.
- Accept schema legality, evidence support, and task completion separately. Real-model evaluation verifies routing and task behavior, not server enforcement.
- Applicable ambiguity tests include candidate clarification, illegal continued calls, multiple calls in one turn, cross-turn choice, permission changes, pagination, and explicit list requests.
- The cost is maintaining contracts, state, and boundary tests. The benefit is independently verifying critical guarantees across prompts and model versions. Natural-language understanding and task coverage still depend on the model.
- The original ADR change fixed development guidance only; it did not itself change business behavior or claim to repair the example. Update or supersede this decision when responsibilities change.

## Implementation record (2026-10-21)

Subsequent repairs added ambiguity state gates at Agent execution entry points, persisted candidate sets, and rechecked conversation, authorization scope, query, and current data on cross-turn choice. The evidence registry accepts only server-registered clarification tables. Incomplete pagination requires a narrower query. Explicit list mode retains multi-object semantics. See [E2 Agent API v1](../../contracts/e2-agent-api-v1.md) for behavior and failure states. Routing and natural-language intent recognition still require real-model evaluation.

## Related guidance

- [Project development agreement](../../AGENTS.md)
- [Agent / MCP boundaries](../agent-boundaries.md)
- [Structured answers and evidence contract](../enterprise/structured-answer-evidence.md)
- [Improvement plan: Extend tools for business gaps](../enterprise/improvement-plan.md#61-extend-tools-for-business-gaps)
