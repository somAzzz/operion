# E3 action-control runbook

E3 runs Action Service, the PostgreSQL ledger, and a separate Worker using only the persistent stub, never Twenty/ERPNext writes. This runbook describes that profile; later E4 acceptance is separate.

## Environment and migration

Use PostgreSQL 16 or compatible. Separate migration/runtime identities. Migration authority creates/grants the non-login `operion_action_app` role; runtime DSN only inherits or switches to that restricted role, owns no schema/table, and cannot migrate. If managed PostgreSQL forbids `CREATE ROLE`, a platform administrator must precreate the role.

```bash
uv sync --extra dev
export OPERION_ACTION_MIGRATION_DATABASE_URL='postgresql://migration-admin@...'
uv run operion-action-migrate

export OPERION_ACTION_DATABASE_URL='postgresql://restricted-action-login@...'
# Only if the restricted login requires explicit SET ROLE:
# export OPERION_ACTION_DATABASE_ROLE='operion_action_app'
export OPERION_ACTION_TOKEN='replace-with-secret'
export OPERION_ACTION_CSRF_TOKEN='replace-with-separate-secret'
export OPERION_ACTION_USER_ID='e3-local-user'
export OPERION_ACTION_TENANT_ID='e3-local-tenant'
export OPERION_ACTION_COMPANIES='AI Demo GmbH'
export OPERION_ACTION_CAN_APPROVE='0'
uv run operion-action-api
```

API/Worker never auto-migrate. The approval service uses a separate identity/credential and explicit `OPERION_ACTION_CAN_APPROVE=1`; default is `0`. Never commit credentials or expose them in browser variables. This static local E3 profile is for isolated acceptance; enterprise identity uses the [E5 boundary](../contracts/e5-enterprise-boundary-v1.md) and server `Principal`.

Health must report `mode=e3_stub_only`, `writes_enabled=false`:

```bash
curl http://127.0.0.1:8001/health
```

## Worker, pause, and recovery

One claim cycle:

```bash
uv run operion-action-worker --once --worker-id e3-worker-1
```

Reconcile all expired in-flight leases:

```bash
uv run operion-action-worker --recover --worker-id e3-recovery-1
```

Recovery reconciles; lease expiry is not proof of no submission. Never directly reset UNKNOWN/RECONCILING/MANUAL_REVIEW to executable. Set `global` or `stub.followup_task` pause through `POST /api/action-pauses`; record reason and finish reconciliation before resuming.

## Acceptance

Unit/integration tests use runner-owned containers. The evaluator/probe below needs a separately prepared isolated evaluation database, never a business database. Prefer a new report directory per rerun; these paths retain the original package names.

```bash
export OPERION_TEST_ACTION_DATABASE_URL='postgresql://...'
uv run ruff format --check src tests
uv run ruff check .
scripts/verify.sh offline
scripts/verify.sh postgres
uv run operion-evaluate-e3 \
  --database-url "$OPERION_TEST_ACTION_DATABASE_URL" \
  --output reports/enterprise/e3/20260920T-action-control/w01-w15.json
uv run operion-probe-e3 \
  --database-url "$OPERION_TEST_ACTION_DATABASE_URL" \
  --output reports/enterprise/e3/20260920T-action-control/capability-matrix.json
```

The probe reads explicitly read-only Twenty credentials from local `.env`, performs schema introspection and `GET /rest/tasks`, and creates no Task. Its E3 `e4_release_allowed=false` report remains historical until separately accepted E4 probes establish a different capability scope.

Web verification:

```bash
scripts/verify.sh web
cd apps/web
npm run dev
```

Verify `/approvals`, `/actions`, and `/actions/{id}` derive state from Action Service; refresh retains it; UNKNOWN/RECONCILING offers no recreate shortcut.

## Fault handling

- Database/audit failure: stop new actions; never bypass the ledger.
- Duplicate effects: global pause; preserve action/attempt/event/target evidence.
- Crash/expired lease: recover by reconciliation, not another submission.
- Multiple matches/digest mismatch: retain MANUAL_REVIEW for investigation.
- Broken event chain: stop writing, preserve database/logs, request independent admin investigation.

A deployment not covered by E4 still needs Task ID uniqueness, relation/partial-write behavior, notification effects, timeout/failure semantics, and exact readback probes before real writes. The existing E4 isolated pass does not release a changed environment automatically.
