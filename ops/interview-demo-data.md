# Interview demo v1 data runbook

This runbook is separate from the WWI and E2 fixtures. It never modifies
`wwi:*`, `operion:e2:*`, F01–F06, stock, invoices, payments, deliveries, or
receipts. The dataset uses `operion:demo:interview-v1:*` keys, `data_class=simulated`,
seed 42, business date 2026-09-15, EUR, and tax-exclusive amounts.

## Prepare and validate

```bash
.venv/bin/operion-etl prepare-interview-demo \
  --output-directory data/canonical/interview-demo-v1 \
  --identity-map reports/interview-demo-v1/identity_map.csv \
  --seed 42 --business-date 2026-09-15

.venv/bin/operion-etl validate-interview-demo \
  --directory data/canonical/interview-demo-v1
```

Preparation is deterministic and replaces files only in the named output
directory. Validation checks fixed counts, all parent/product links, zero-order
edge cases, the customer with at least eight orders, and line-to-header totals.

## Dry-run plan (the default)

```bash
.venv/bin/operion-etl provision-interview-demo \
  --directory data/canonical/interview-demo-v1 \
  --identity-map reports/interview-demo-v1/identity_map.csv
```

This performs no network writes. It lists target objects, dependencies, side
effects, and apply gates. Suppliers are ERPNext-only; they are not disguised as
Twenty Companies.

## Guarded apply

Use a dedicated, untracked admin environment file. It must contain the target
URLs and provisioning keys plus all of these safeguards:

```dotenv
OPERION_DEMO_INSTANCE=1
OPERION_DEMO_BACKUP_CONFIRMED=1
OPERION_DEMO_BACKUP_PATH=/absolute/path/to/a/verified/backup
OPERION_DEMO_RESTORE_COMMAND=the-reviewed-restore-command
OPERION_DEMO_EXTERNAL_EFFECTS_DISABLED=1
OPERION_COMPANY=AI Demo GmbH
```

Then explicitly apply:

```bash
mkdir -p reports/interview-demo-v1/<run-id>
cp reports/interview-demo-v1/identity_map.csv \
  reports/interview-demo-v1/<run-id>/identity_map.prepared.csv

.venv/bin/operion-etl provision-interview-demo \
  --directory data/canonical/interview-demo-v1 \
  --identity-map reports/interview-demo-v1/<run-id>/identity_map.prepared.csv \
  --apply --admin-env /absolute/path/to/interview-demo-admin.env
```

The apply path resolves every record by the stable source-key field. Consistent
records are reused; a changed name or non-draft demo order is a conflict and is
not overwritten. New orders stay in native draft state. The loader never changes
global naming, permissions, stock settings, or mandatory-field rules, and never
submits an order.

## Independent readback and reconcile

After apply, use read-only credentials and current permission evidence:

```bash
.venv/bin/operion-etl reconcile-identities \
  --identity-map reports/interview-demo-v1/<run-id>/identity_map.prepared.csv \
  --output reports/interview-demo-v1/<run-id>/identity_map.reconciled.csv \
  --report reports/interview-demo-v1/<run-id>/identity-readback.json \
  --target twenty --target erpnext \
  --erpnext-permission-evidence /absolute/path/to/current-readonly-evidence.json
```

Do not treat CSV generation, an HTTP success, or a returned target name as final
completion. Review the reconcile report for missing, unexpected, and conflicting
keys before switching runtime configuration to the reconciled map.

## Runtime modes and scope

Snapshot mode is explicit and never makes network calls:

```bash
export OPERION_DATA_MODE=snapshot
export OPERION_CANONICAL_DIR=data/canonical/interview-demo-v1
export OPERION_IDENTITY_MAP=reports/interview-demo-v1/identity_map.csv
export OPERION_CUSTOMER_IDS="$(printf 'operion:demo:interview-v1:customer:%03d,' {1..10} | sed 's/,$//')"
export OPERION_SUPPLIER_IDS="$(printf 'operion:demo:interview-v1:supplier:%03d,' {1..5} | sed 's/,$//')"
export OPERION_OBSERVED_AT=<actual-snapshot-observation-ISO-8601>
```

Live mode requires the same canonical roster, reconciled identity map and scopes,
plus both read-only keys. It performs GET-only reads on each tool call and returns
`source_unavailable` instead of silently falling back:

```bash
export OPERION_DATA_MODE=live
export TWENTY_API_KEY_READ_ONLY=<read-only-key>
export ERPNEXT_API_KEY_READ_ONLY=<api-key:api-secret>
```

Provisioning credentials must not be exported into the Agent, MCP, browser, or
web process.
