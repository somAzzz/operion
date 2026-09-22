# Operion interview readiness

Evidence date: 2026-09-22 Europe/Berlin. This report separates current-run
evidence from older accepted evidence. No WWI business object was written to
Twenty or ERPNext during this run.

## Outcome

The WWI snapshot query demo and the original E2 controlled-action demo are both
runnable through the same production-built web application. WWI queries use
`interview-wwi-v1`, mapping revision `interview-wwi-v1.1`, with an exact
10-customer/5-supplier server scope. The E2 profile retains F01–F06 and the
reconciled E2 identities. The profiles intentionally share ports and are
switched, not run together.

The first WWI import is planned but blocked and was not applied. The target
company and price lists are EUR while WWI's USD is only a dataset assumption;
three required target Items also have conflicting native stock-item semantics.

## Fixed defects

- WWI `PickedQuantity` now maps to `picked_quantity`. `unpicked_quantity` is
  stored separately. `delivered_quantity` and delivery-open quantity remain
  blank when the WWI order line provides no delivery evidence. Existing E2
  delivery semantics are unchanged.
- The UI and Agent say that picked is not delivered, show unknown delivery, and
  keep WWI source status separate from ERPNext native status. A real Agent run
  initially called WWI `finalized` “confirmed/non-draft”; the prompt contract was
  corrected and the repeated answer now explicitly says native status is absent.
- Purchase imports now use `ordered_outers × units_per_outer` as base quantity,
  mapped base UOM, conversion factor 1, and a base-unit rate at target precision.
  The loader verifies both source outer-price arithmetic and target line amount.
- The hand-written gold case is 1,592 × 25 = 39,800 units; 39,800 × 1.90 =
  75,620.00. It cannot regress to 3,024.80. Factors 1, 10, and 24 and a repeating
  unit rate are covered; an insufficient target precision fails closed.
- Existing-object confirmation now compares business key, party relation,
  company, currency, UOM, quantity, conversion factor, rate, line amount, child
  keys, links, and native `docstatus`. Same-name or same-PO records with different
  content are conflicts, never overwrite candidates.
- `dataset.json` records mapping revision `interview-wwi-v1.1` and its semantic
  changes. The pinned raw WWI snapshot was not modified and no third dataset was
  created.
- Empty results, counts, and date ranges are explicitly limited to the current
  dataset and server-authorized scope. Customers 60 and 88 have zero extracted
  orders; this is not a claim about the complete WWI database.
- The AG-UI stream now holds an early `TOOL_CALL_END` until any late SGLang JSON
  argument fragments have arrived. The combined five-step customer/order prompt
  was re-run with three complete tool calls and zero protocol-order violations.
- Both interview profiles allow seven model requests and six tool calls, with
  100,000 cumulative input tokens, 4,000 output tokens per model request, 12,000
  cumulative output tokens, and a 90-second run timeout. Per-request output and
  run-wide output are separate controls; invalid request/tool and output-budget
  combinations fail at startup. The served model has a 262,144-token context.
- Five complex Web → Agent → SGLang → tool cases pass: customer chain, supplier
  chain, two-order comparison, two zero-order customers, and a four-tool
  customer/supplier cross-domain comparison. Every call had ordered
  START/ARGS/END/RESULT events, no active call at finish, and required answer
  semantics. Run with `scripts/verify-interview-complex-cases.py`.
- Browser failure handling was checked with a deliberate seven-tool request.
  All seven cards terminate as errors rather than remaining on Loading, while
  the page shows a stable work-budget message and hides Pydantic internals.
- The composer now remains mounted and editable while a run is active. A
  follow-up can be queued, the queued text is visible and removable, and a
  terminal error is repeated next to the input with an explicit recovery
  message. The conversation is retained instead of replacing the composer.
  A live seven-tool request returned sanitized `LIMIT_EXCEEDED`; the next
  narrow request on the same thread completed with `RUN_FINISHED`.
- Actual request bytes are checked before AG-UI parsing even when the Next.js
  proxy omits or a client falsifies `Content-Length`.

## Start and stop

Build once:

```bash
cd /home/bo/projects/python/operion/apps/web
npm ci
npm run build -- --webpack
```

WWI basic query profile:

```bash
cd /home/bo/projects/python/operion
./scripts/interview-demo.sh start-wwi
./scripts/interview-demo.sh status
# UI: http://127.0.0.1:3100
./scripts/interview-demo.sh stop
```

Original E2 controlled-action profile:

```bash
cd /home/bo/projects/python/operion
./scripts/setup-interview-action-db.sh
./scripts/interview-demo.sh start-e2
./scripts/interview-demo.sh status
# UI: http://127.0.0.1:3100
# approvals: http://127.0.0.1:3100/approvals
./scripts/interview-demo.sh stop
```

The script generates service and CSRF tokens in process memory, keeps them out of
the repository and effective-config report, and records only its own PIDs. It
does not start the action Worker. The E2 action database is
`operion_action_demo`; PostgreSQL regression uses the separate
`operion_action_test` database in the same isolated local container.

## Effective profiles

### WWI basic query

- Dataset: `data/canonical/interview-wwi-v1`
- Mapping: `interview-wwi-v1.1`
- Mode/class: `snapshot`, `public_sample`
- Historical business date: 2016-05-31
- Source snapshot acquisition: 2026-09-12T10:03:59.810871+00:00
- Observation time: set to the real UTC service start time; last verified start
  was 2026-09-22T06:39:14Z
- Customer scope: WWI IDs 58, 60, 65, 88, 183, 463, 840, 935, 961, 1011
- Supplier scope: WWI IDs 3, 6, 7, 8, 9
- Identity map: 190 pending rows, zero populated target IDs. Blank pending IDs
  are not rendered as real system links.
- Agent run budget: 7 model requests, 6 tool calls, 100,000 cumulative input,
  4,000 output per request, 12,000 cumulative output, 90 seconds.

### E2 controlled action

- Dataset: `data/canonical/operion-e2-demo-v1`
- Mode/class: `snapshot`, public-sample plus simulated F01–F06 fixtures
- Customer scope: only `ambiguous-a` and `ambiguous-b`
- Identity map: the accepted reconciled E2 map
- Action identities: proposer `e2-demo-user`; approver `e4-approver`
- Model endpoint: SGLang at `http://127.0.0.1:30000/v1`, served model
  `qwen3.8-27b`; actual container model is
  `RadixArk/Qwen3.8-27B-NVFP4` revision
  `554ebba9b5f1b79dc11246341960360e6ef05ef4`
- Agent run budget: 7 model requests, 6 tool calls, 100,000 cumulative input,
  4,000 output per request, 12,000 cumulative output, 90 seconds.

No wildcard customer or supplier scope is used in either profile.

## Checkable WWI questions and answers

These answers were checked against the committed CSVs and repository tools; the
two continuous conversations below also ran through Web `/api/agent`, Agent,
SGLang, and the server-side tools.

1. “Find customers whose names contain Tailspin Toys.” — 5 matches: IDs 58, 60,
   65, 88, and 183; the Agent asks for a canonical ID instead of guessing.
2. “How many orders does customer 65 have?” — 10 selected orders totalling USD
   5,742.50 in this dataset and authorized scope.
3. “Does customer 60 have any orders?” — zero in this extracted dataset and
   authorized scope; no conclusion is made about complete WWI.
4. “Does customer 88 have any orders?” — the same scoped zero-order result.
5. “What are the current sales order date range and total amount?” — 30 selected
   orders from 2014-07-22 through 2016-05-26, USD 26,338.80 tax-exclusive,
   scoped to this dataset.
6. “What is the quantity status of order 66823?” — line 210128 ordered 48,
   picked 48, unpicked 0, delivered unknown; no WWI order-line delivery evidence
   exists.
7. “Which suppliers are authorized?” — 5: Consolidated Messenger, Humongous
   Insurance, Litware, Lucerne Publishing, and Nod Publishers.
8. “How many purchase orders does Litware have?” — 15 selected complete orders,
   dated 2016-05-12 through 2016-05-31; source states are 14 `finalized` and 1
   `open`, not ERPNext native states.
9. “What is the amount of the first line in purchase order 2044?” — 1,592 outers
   × 25 = 39,800 Each at USD 1.900000, amount USD 75,620.00.
10. “What is the total amount of purchase order 2044?” — three lines USD
    75,620.00 + 105,062.40 + 542,640.00 = USD 723,322.40.
11. “Does Consolidated Messenger have any purchase orders?” — zero in this
    extracted dataset and authorized scope only.

## Continuous conversation acceptance

Customer → order → line, actual Web/Agent run:

1. User searched `Tailspin Toys`; Agent returned five stable IDs and requested a
   choice.
2. User selected `wwi:organization:customer:65`; Agent returned two contacts and
   all 10 selected orders.
3. User opened `wwi:sales_order:66823`; Agent returned line 210128 as ordered 48,
   picked 48, unpicked 0, delivered unknown, and explicitly stated picked does
   not mean delivered.

Supplier → purchase order → line, actual Web/Agent run:

1. User searched `Litware`; Agent resolved supplier 7 and listed 15 selected
   purchase orders.
2. User opened `wwi:purchase_order:2044`; Agent returned all three complete
   lines, base quantities and prices, and reconciled USD 723,322.40.
3. After the status-contract correction, a repeated run said `finalized` is a
   WWI source status, `native_status` is absent, and no ERPNext Draft/Submitted
   state can be inferred.

## Regression evidence

### Deterministic business tests — PASS

- Full Python suite with isolated PostgreSQL configured: 136 PASS, 0 FAIL,
  0 SKIPPED (final run; see commands below).
- WWI/demo mapping subset before the final run: 27/27 PASS.
- Gold quantities and amounts are independent constants in the validator/tests,
  not calculated with the loader helper under test.
- Next.js production build and TypeScript: PASS.

### PostgreSQL action control — PASS

- Previously skipped group: 23 executed, 23 PASS, 0 FAIL, 0 SKIPPED.
- Includes cross-tenant denial, rejection of forged/raw proposals, exact revision
  approval, no self-approval, strict parameter binding, immutable hash-chained
  audit, response loss, idempotency, concurrent workers, lease recovery,
  reconciliation, permission/scope checks, and compensation separation.
- Reproduce:

```bash
./scripts/setup-interview-action-db.sh
export OPERION_TEST_ACTION_DATABASE_URL='postgresql://operion_test:operion_test_local_only@127.0.0.1:55432/operion_action_test'
PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest -v tests.test_action_app tests.test_action_control
```

### Real upstream read-only — PASS

- GET-only identity comparison at 2026-09-21T22:30:10Z: Twenty 39/39 and
  ERPNext 94/94; zero missing, unexpected, or target-ID mismatches.
- Target identity: Twenty 2.39.0 at localhost:3000; ERPNext 16.34.2 at
  localhost:8080; ERP company `AI Demo GmbH`.
- A formal reconciliation with the old permission report was correctly blocked
  because the report is older than 24 hours. It was not timestamp-forged.

### Twenty execution adapter

- Deterministic adapter tests: 4 PASS, including deterministic IDs, response-loss
  reconciliation, content mismatch/manual review, and no repeated mutation.
- Prior accepted real E4 evidence remains at
  `reports/enterprise/e4/20260920T-followup-task/live-fault-evaluation.json` and
  records response-loss and concurrent/crash recovery against the isolated
  workspace.
- Current run actual Twenty write: NOT RUN. No Worker was started because this
  run did not receive approval for a new downstream side effect.

### Agent and web flow

- Original E2 model evaluation initially produced 39/45; C02 used search rather
  than the required ambiguity-returning overview tool, and A02 trusted the
  user's outage claim rather than checking. The failed report is preserved as
  `e2-agent-evaluation.initial-failed.json`.
- After tightening the tool contract, the complete repeat was 45/45 PASS.
  F01–F06 were 18/18 in both runs.
- Current E2 HTTP acceptance: Agent health, home, and `/approvals` returned 200.
- Current local-ledger action: F03 proposal
  `f7978194-7c23-48f6-ab8f-b619900afbb3` was proposed by `e2-demo-user` and
  approved at exact revision 1 by `e4-approver`. The independent Twenty readback
  found zero Tasks with that ID because the Worker was intentionally not run.
- Browser click flow: BLOCKED. The available computer-use inventory returned no
  browsers or apps. HTTP/AG-UI end-to-end was completed as the verifiable
  alternative; build success alone is not counted as browser success. The
  composer recovery change was production-built and its terminal-error → next
  successful-run sequence was verified through the same Next.js `/api/agent`
  SSE proxy, but the new queued-message controls were not falsely marked as a
  browser click pass.

## WWI read-only import plan

The current pending identity map was compared with live target source keys and
object content. A batch ID alone never authorizes duplicate target objects.

| Scope | REUSE | CREATE | CONFLICT |
|---|---:|---:|---:|
| Full Twenty | 0 | 24 | 0 |
| Full ERPNext | 3 | 156 | 7 |
| Full total | 3 | 180 | 7 |
| First dependency-closed batch | 3 | 10 | 3 |

Full-batch reuse is supplier 7 and contacts 2/33. Conflicts are Items 184, 193,
204 (existing native `is_stock_item=1`, proposed value 0), purchase order 2074
(existing EUR vs dataset-assumed USD), and its three child lines because their
parent relation is conflicting. The three child quantities/UOM/rates/amounts
themselves match the corrected base-unit mapping.

The first batch is exactly customer 65, supplier 7, contacts 2/33/1129, products
184/193/204, complete sales order 66823 and complete purchase order 2044. It is
blocked by the three Item conflicts and unresolved currency policy.

Dry-run command:

```bash
.venv/bin/operion-etl provision-interview-wwi \
  --selection-plan config/interview/wwi-first-batch-selection.json
```

Proposed apply command, not authorized and not executed:

```bash
.venv/bin/operion-etl provision-interview-wwi \
  --identity-map reports/interview-wwi-v1/<approved-run>/identity_map.prepared.csv \
  --selection-plan config/interview/wwi-first-batch-selection.json \
  --apply --admin-env /absolute/path/to/reviewed-wwi-admin.env
```

The target company and Standard Buying/Selling price lists are EUR. WWI rows do
not carry a source currency code; USD is only the dataset-level assumption. No
current or historical exchange rate was invented. Approval must specify whether
to retain document USD and which reviewed 2016 conversion rate/policy applies to
the EUR company ledger.

## Backups and side effects

Actual backup time: ERPNext reported 2026-09-22 00:09:17 Europe/Berlin. Local
backup directory:
`var/backups/20260921T220915Z` (the directory uses UTC).

- Twenty: custom-format PostgreSQL dump plus `.local-storage` tar.gz.
- ERPNext: database SQL gzip, public/private file archives, and site config
  backup.
- `SHA256SUMS` verifies all six files. `gzip -t`, tar listing, and
  containerized `pg_restore -l` all passed.
- Recovery must first restore into uniquely named temporary databases/sites and
  compare counts. For Twenty use `pg_restore` into a new PostgreSQL database and
  extract storage into a new temporary volume. For ERPNext copy the four files
  into the backend and use `bench --site <temporary-site> restore` with explicit
  database/public/private file arguments. Do not overwrite the running instances
  as a casual rollback.

Side-effect inspection found one active Twenty workspace member and the expected
internal record-created timeline activity contract. ERPNext has no Email Account
or Webhook records, but two enabled email Notifications: Material Request Receipt
and New Fiscal Year. They do not target these draft orders, but must be rechecked
before any write. Setting an environment flag was not treated as proof.

## Final status ledger

PASS:

- WWI mapping/amount correction and gold cases.
- 141 deterministic/unit/integration tests with the test database configured.
- 23/23 PostgreSQL action-control tests.
- Web production build and actual HTTP routes.
- WWI natural-language customer and supplier chains through the live model.
- Five complex live-model cases and normal/error Chrome rendering paths.
- E2 Agent evaluation 45/45 after correction.
- GET-only upstream identity comparison, real backups, and backup integrity.
- Local proposal → different-user exact-revision approval with immutable events.

FAIL:

- No unresolved current regression failure. The initial 39/45 Agent run is
  retained as resolved failure evidence, not deleted.

SKIPPED:

- 0 in the final Python suite; the previously skipped 23 database tests were
  actually executed.

NOT RUN:

- New real Twenty Worker execution in this run.
- WWI first-batch apply, independent post-write readback, second idempotency run,
  remaining batch, and live-mode switch.

BLOCKED:

- WWI first batch: three native Item conflicts plus unresolved USD-assumption to
  EUR-company policy.
- Browser click automation: no browser/app was exposed by the computer-use
  inventory.
- Fresh ERPNext protected-DocType permission attestation: the existing evidence
  is stale, and this read-only stage did not run write-denial probes.

These blockers must be cleared and a specific `import-plan.json` revision
explicitly approved before any target-system apply or Worker execution.
