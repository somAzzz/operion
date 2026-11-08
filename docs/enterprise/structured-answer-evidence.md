# Structured answers and evidence contract

Implemented on 2026-10-17: runtime policy `structured-evidence-v1` replaces `business-facts-v2`. `answer_claims.py` and `business_facts.py` were removed. Business facts are no longer inferred from natural-language or Markdown output. See [ADR-001](../architecture/adr-001-deterministic-agent.md) and the [current implementation queue](improvement-plan.md).

## Data flow

1. The server authenticates, authorizes, and executes existing business tools. Tools retain responsibility for reading data and checking object permission.
2. `EvidenceRegistry` normalizes known tools and versioned results into random references valid only for this run and authorization scope. Facts include entity, field, value, currency, coverage, JSON pointer, and source context; tables contain server-defined rows and columns.
3. Tools return an `answer_evidence` manifest. The model submits a strict `AnswerPlan` through `present_answer`, selecting only current fact IDs, table IDs, and allowed columns. It cannot submit business prose, custom titles, numbers, currencies, row data, or claims of complete source history.
4. Validate references, context, fields, duplicate selections, and evidence conflicts. Invalid selections allow one model repair; continued failure produces no business answer. Ordinary text has no default allow path.
5. The server generates English answers from fixed semantic labels and evidence. It validates again before SSE publication. Model intermediate text, output-tool arguments, and unverified partial answers are not published. Only final server-rendered text enters successful conversation history. `AnswerPlan.language` accepts only `en`. Source values and quoted user statements are escaped without translation.
6. Final `ModelResponse.metadata["operion.answer_evidence"]` stores selected fact/table evidence for audit and acceptance. The public browser history API retains its existing message structure. Old history is not rewritten; failed/cancelled runs save no new answer.

## Verification boundaries

| Scenario | Constraint |
| --- | --- |
| Customer population versus customers with orders | `customer_count` and `customers_with_orders` are independent. A complete order list proves the latter, not the total customer population |
| Pagination and totals | `page_order_count` comes from returned rows. Filtered totals require explicit `completeness.total_count` or an organization summary. Paged customer distribution is not a complete distribution |
| Entities and amounts | Tables cannot alter or reorder values. Projections retain identity columns, currency with amounts, and units with quantities. Unknown currency suppresses the amount while other evidence remains usable; invalid amounts cannot become valid evidence |
| State | Source, business, document, picking, and delivery states retain their own field semantics |
| Missing and zero | `None`, unexposed fields, and source failures cannot produce zero facts. Explicit zero remains displayable. Contact fields preserve `present`, `explicit_empty`, and `not_exposed` |
| Freshness and coverage | Bind run, tenant/user/scope, tool, filters, source mode, business date, observation time, completeness, and source warnings. Snapshot fulfillment cannot be presented as live |
| Conflict and scope | Contradictory evidence for the same object/field cannot be chosen arbitrarily. An out-of-scope related object rolls back the entire normalization |
| Operation capability | Capability checks do not prove execution. Proposals accept only `PENDING_APPROVAL` and explicitly state that execution has not occurred. Approval/Worker gates remain independent |
| Source text | Escape source strings such as names as Markdown/HTML data, never as model instructions, column labels, or arbitrary answer prose |
| Ambiguity clarification | `needs_details` accepts only server-registered candidate/search tables. List-mode search results are registered when clarification is requested, not for ordinary list answers. Other business tables and forged references cannot serve as clarification. The server fixes the selected table and notice; incomplete pages require a narrower query |

This validates **evidence support for selected facts**. The model can still choose the wrong tool, omit facts, or fail the task. E2 therefore independently checks tool choice, arguments, and whether required facts actually appear in the answer. Schema legality is not task completion. Tools and sources remain the trust boundary for facts. Unknown tools or contract versions cannot produce valid evidence. Complex calculations, tax, and currency conversion require typed, source-backed domain capabilities exposed through new contracts; never restore an unconstrained business-prose channel.

## Regressions and observation

- `test_business_fact_binding.py`: the two recorded false-rejection incidents (total 30/page 1; 30 orders/8 customers with orders), English rendering and schema-enforced language selection, immutable entity/field/currency/scope bindings, old-run/cross-scope references, conflicts, and sales/purchase distinction.
- `test_output_guardrails.py`: zero/missing/failure, unknown contracts, projections, fulfillment, proposals/capability, source injection, and empty/duplicate/forged references.
- `test_answer_evidence_contracts.py`: actual repository outputs exercise read-tool adapters instead of relying only on hand-written response shapes.
- `test_agent_app.py`: invalid output never enters SSE/successful history; final and restored text agree; permission changes retain visible conversation while refreshing model context; cancellation publishes no partial answer.
- `test_e2_evaluation.py` and both `accept_guardrails*.py` scripts: score selected structured evidence. Real-model expectations still come independently from CSV or read-only source APIs.

Langfuse `operion.guardrail.output_facts` records stable reason codes, policy version, fact/table counts, and known references. Unknown model-supplied reference strings do not enter content-disabled diagnostics. Tool-contract errors use `operion.guardrail.evidence_contract`. The final run span records the validated reference plan; business content follows the existing capture switch. Validation does not depend on Langfuse availability.

Rerun with `scripts/verify.sh offline`; focus with `scripts/verify.sh case fact-binding`. Real-model command: `PYTHONPATH=src .venv/bin/python scripts/accept_guardrails.py --output /tmp/operion-guardrails.json`. Database checks use the existing isolated PostgreSQL workflow. The structured-answer implementation did not change the database schema.

## Historical acceptance results (2026-10-17)

These are the recorded implementation results, not a new acceptance run for the current worktree.

- Offline: 237 tests, 213 passed, 24 isolated PostgreSQL integration tests skipped under the offline workflow; Ruff and `git diff --check` passed.
- Real qwen3.8-27b → FastAPI → AG-UI: counts, amount/currency, write denial, and forged-reference denial, 4/4 passed with independent CSV expectations. Local report: `/tmp/operion-guardrails-structured-acceptance.json`.
- The local development Gateway Agent was rebuilt. Browser checks verified total customers 10, a complete 30-row sales table, filtered total 30/page 1, and customer population 10/customers with orders 8/orders 30. Refresh restored final text and previous history.
- Data was the `demo-wwi-v1` public-sample snapshot. Online ERPNext/Twenty and PostgreSQL integration acceptance were not rerun. Online acceptance scripts were migrated to the new contract and passed import checks.
- Read-only Langfuse inspection found both checks for browser run `Ey2cy7J` were `GUARDRAIL / DEFAULT / STRUCTURED_EVIDENCE_SUPPORTED`, policy `structured-evidence-v1`: [trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/44cf2e3adc3838c45bbb0f86b5670265).
