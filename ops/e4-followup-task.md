# E4 internal follow-up Task runbook

E4 enables only `twenty.followup_task` on the E3 ledger, in the isolated public/simulated demonstration workspace. Enterprise use additionally obeys [E5 gates](e5-enterprise-pilot.md).

## Credential separation

- Agent: read-only Twenty/ERPNext credentials and restricted action-database identity; proposal creation only.
- Action API: ledger credential, no Twenty write key.
- Worker: ledger, dedicated Twenty write key, and ERPNext read key.

Agent must not load an admin-key `.env`. Inject only the intended read values explicitly:

```bash
export OPERION_ENABLE_FOLLOWUP_PROPOSALS=1
export OPERION_ACTION_DATABASE_URL='postgresql://restricted-action-login@...'
export OPERION_ACTION_TENANT_ID='operion-demo'
export OPERION_FOLLOWUP_ASSIGNEE_ID='<fixed Twenty workspace-member UUID>'
export TWENTY_API_KEY_READ_ONLY='<read-only key>'
export ERPNEXT_API_KEY_READ_ONLY='<api-key:api-secret>'
# Also set E2 canonical, identity-map, scope, and observation variables.
uv run operion-agent
```

Proposer and approver are different server identities. Approver example:

```bash
export OPERION_ACTION_USER_ID='e4-approver'
export OPERION_ACTION_TENANT_ID='operion-demo'
export OPERION_ACTION_COMPANIES='AI Demo GmbH'
export OPERION_ACTION_CUSTOMER_IDS='operion:e2:organization:customer:ambiguous-a'
export OPERION_ACTION_CAN_APPROVE=1
uv run operion-action-api
```

Only Worker may load `TWENTY_API_KEY` from `.env`:

```bash
export OPERION_ACTION_DATABASE_URL='postgresql://restricted-action-login@...'
uv run operion-action-worker --once --worker-id e4-worker-1
```

Never configure the write key in Next.js, Agent, MCP, or Action API.

## Operation

1. Agent runs `check_fulfillment`, proposing only a verified `shortfall` through `propose_followup_task`.
2. On `/approvals`, check Company, ERPNext order, owner, title/body, dueAt, revision, digest, and all three effects.
3. A different identity approves the exact revision.
4. Worker atomically claims and revalidates current Company/order/assignee before sending.
5. Follow `/actions/{action_id}` events; only `SUCCEEDED` permits presenting the verified Twenty Task link.

For UNKNOWN/RECONCILING/MANUAL_REVIEW, do not submit another proposal or manually duplicate creation. Recover expired leases:

```bash
uv run operion-action-worker --recover --worker-id e4-recovery-1
```

Immediately reconcile a specific UNKNOWN/RECONCILING action:

```bash
uv run operion-action-worker --reconcile <action_id> --worker-id e4-recovery-1
```

## Reproduce acceptance

Prepare isolated PostgreSQL and migrate under the E3 runbook. The evaluator needs that separate isolated database; never use a business database. Keep historical output intact by selecting a new report directory for new runs.

```bash
export OPERION_TEST_ACTION_DATABASE_URL='postgresql://...'
uv run ruff format --check src tests
uv run ruff check .
scripts/verify.sh offline
scripts/verify.sh postgres
uv run operion-evaluate-e4 \
  --database-url "$OPERION_TEST_ACTION_DATABASE_URL" \
  --live-report reports/enterprise/e4/20260920T-followup-task/live-fault-evaluation.json \
  --output reports/enterprise/e4/20260920T-followup-task/w01-w15.json
scripts/verify.sh web
```

Real fault drills use new action IDs. Check zero Tasks before approval; UNKNOWN after response loss; exact-ID recovery; one claim with two Workers; reconciliation before resending after lease expiry; one Task/TaskTarget with exact fields.

## Pause, faults, and compensation

- Wrong target, duplicate Task, or unknown external notification: pause `twenty.followup_task` immediately.
- Changed precondition: retain CONFLICT; create a new proposal, never overwrite old approval.
- Wrong content/deterministic ID: retain MANUAL_REVIEW and compare target/revision.
- Task present/Target absent: only recovery may complete the deterministic Target.
- Authorized people mark test/erroneous Tasks DONE in Twenty and record action/reason; no database deletion.
- Reprobe effects after membership/email/workflow/notification changes before resuming writes.

E4 releases only isolated internal Task creation. Actual identity/data, durable audit/backups, alerts, and release operations require E5 plus independent write-specific acceptance.
