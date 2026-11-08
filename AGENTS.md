# Operion development agreement

This file defines the project's architecture and review requirements. Existing global execution agreements still apply. The supervision and delegation workflow is enabled only when the user explicitly invokes `$sol-sglang-build`.

## Read before changing behavior

For work involving the Agent, tools, business semantics, or answer behavior, read:

- [ADR-001: Deterministic business capabilities and a controlled Agent](docs/architecture/adr-001-deterministic-agent.md)
- [Agent / MCP boundaries](docs/agent-boundaries.md)
- [Structured answers and evidence contract](docs/enterprise/structured-answer-evidence.md)
- The relevant capability contracts in `contracts/` and their tests.

## Responsibility boundaries

- The model understands requests, selects capabilities, and organizes evidence. Domain services own business calculations, entity resolution, and state semantics.
- The server owns authentication, authorization, workflow state, budgets, execution gates, and fact verification. Model intent, tool descriptions, and tool visibility never replace execution-time checks.
- Business facts may be published only through valid evidence references and deterministic rendering. Do not add free-form business text that bypasses `AnswerPlan` / `EvidenceRegistry`.
- Typed capabilities require verifiable inputs, explicit result and error semantics, provenance, authorization scope, and completeness. Type annotations alone do not guarantee reliability.
- Agent and MCP entry points reuse the same business rules, authorization, and result semantics.

## Order of repair decisions

1. Locate the failure using sessions/traces, tool inputs/outputs, and relevant code. Identify the violated invariant and responsible layer. Distinguish facts from hypotheses when evidence is incomplete.
2. Prefer a repair in the relevant domain service, typed contract, runtime state, or evidence verification/rendering layer. Extend existing capabilities first; expose a new model-visible tool only for an independent business task.
3. Prompt changes, tool descriptions, or increased call budgets alone cannot complete a correctness, permission, entity ambiguity, workflow-gate, or evidence-verification repair.
4. Once capabilities and server guarantees exist, prompts/descriptions may improve routing, language, and interaction. Identify the remaining model dependency and evaluate task completion.
5. Preserve the distinctions among missing values, explicit zero, no results, no permission, upstream failure, and insufficient evidence. Preserve pagination, freshness, currency, and unit semantics.

## Verification and code review

- Behavior repairs need a regression that fails before and passes after the repair, directly testing the layer that enforces the guarantee. Prompt-string tests or one successful real-model run cannot replace behavior verification.
- For critical invariants, force incorrect model choices, forged references, and continued calls to verify that the server still blocks illegal paths. Cover direct tool entry points, multiple calls in one turn, and cross-turn state as applicable.
- Validate schema legality, evidence support, and user-task completion separately. Passing the first two does not prove the third.
- Reuse applicable `scripts/verify.sh` entry points: `offline`, `case`, `postgres`, and `web`. Select checks by scope; documentation-only changes need content, link, and diff checks.
- Report the root cause, enforcement layer, actual verification results, and remaining model dependencies. Never count unexecuted, skipped, or blocked checks as passed.
- Flag changes that move business rules into prompts, weaken evidence validation, hide tools without execution gates, or fork Agent/MCP rules. Responsibility-boundary changes require corresponding architecture decisions and contracts.
- Preserve existing uncommitted changes. Do not overwrite, revert, or mix in unrelated work.

## Code Quality

- Before completing a code change, apply [lean-comments](.agents/skills/lean-comments/SKILL.md) to the source and declaration documentation affected by the change.
- Explain a business rule, invariant, or constraint in a comment only when the code and tests leave its rationale unclear. Omit comments that narrate the implementation. Keep architectural decisions in the relevant ADR.
- Document what callers need to use a public API or tool safely, including non-obvious authorization requirements, side effects, and error semantics. Keep shared rules in the capability contract. Before editing a tool docstring, check whether it supplies the model-visible tool description.

## Git Commits

- Apply [git-commit](.agents/skills/git-commit/SKILL.md) before every requested commit. A request to edit files or draft a commit message does not authorize a commit.
- Keep each commit to one logical change. Inspect the full staged diff before committing; exclude unrelated edits and preserve any unrelated work already staged by the user.
- Follow Conventional Commits. Use an imperative summary and keep the entire subject, including type and optional scope, to 72 characters or fewer. Add a body only when the reason or impact needs more context than the subject provides.
- Run the checks relevant to the staged change before committing, as described under [Verification and code review](#verification-and-code-review).
- Never push without explicit user authorization.
