# E2 evaluation data runbook

This runbook prepares the isolated `operion-e2-demo-v1` evaluation batch without
changing any historical WWI records. The batch adds two simulated customers with
the same display name, one customer with no orders, and real ERPNext documents for
the six fulfillment cases.

## Credentials and safety boundary

- `ERPNEXT_API_KEY` and `TWENTY_API_KEY` are provisioning credentials. Use them
  only with `seed-e2-targets`; never inject them into the MCP server or Agent.
- Runtime readback uses `ERPNEXT_API_KEY_READ_ONLY` and
  `TWENTY_API_KEY_READ_ONLY`.
- The ERPNext permission gate protects Customer, Supplier, Item, Sales Order,
  Purchase Order, Warehouse, Bin, and UOM. Every one must be readable while
  create, update, delete, submit, cancel, and amend are denied. Contact and ToDo
  are documented non-critical exceptions.
- Custom DocPerm entries for Warehouse, Bin, or UOM must retain the standard
  roles as well as `Operion Read Only`; replacing the standard rows breaks normal
  administrator access.

Do not print `.env` or include API credentials in reports. Back up both systems
before the first seed. For the 2026-09-19 seed, the ERPNext backup is under
`sites/erp.localhost/private/backups/20260919_200848-erp_localhost-*` in the bench
container and the Twenty dump is
`reports/enterprise/e2/20260919T-preseed/backups/twenty.dump`.

## Prepare the canonical batch

```bash
PYTHONPATH=src .venv/bin/python -m operion_etl prepare-e2-data \
  --base-directory data/canonical/wwi-v1-small-20260919-e1 \
  --base-identity-map reports/enterprise/e1/20260919T-e1-complete/identity_map.csv \
  --output-directory data/canonical/operion-e2-demo-v1 \
  --output-identity-map reports/enterprise/e2/<run-id>/identity_map.prepared.csv
```

The preparation step is deterministic. It replaces only records carrying an
`operion:e2:*` canonical ID in its output batch. It does not edit the source E1
batch or any `wwi:*` row.

## Seed the target systems

Copy the prepared identity map to the run's working identity map, then seed:

```bash
cp reports/enterprise/e2/<run-id>/identity_map.prepared.csv \
  reports/enterprise/e2/<run-id>/identity_map.csv

PYTHONPATH=src .venv/bin/python -m operion_etl seed-e2-targets \
  --identity-map reports/enterprise/e2/<run-id>/identity_map.csv \
  --report reports/enterprise/e2/<run-id>/seed-report.json
```

The loader upserts by stable Operion source keys. Repeating it must return the
same Twenty UUIDs and ERPNext document names. Delivery Note lookup uses the
linked Sales Order and ignores cancelled notes, because ERPNext does not retain
the seed marker in the submitted note's `remarks` field.

The seed enables ERPNext stock reservation and partial reservation and keeps
negative stock disabled. The original environment had stock reservation disabled.
Customer naming is switched to a naming series only while creating the two
same-name fixtures and is restored afterward.

Expected live fixture shape:

- two Twenty Companies and two People with `operion:e2:*` external IDs;
- two ERPNext Customers and two Contacts;
- one submitted opening Stock Entry, seven submitted Sales Orders, two submitted
  Purchase Orders, one active submitted partial Delivery Note, and one active
  Stock Reservation Entry;
- F01–F06 use six separate products so their stock facts cannot contaminate one
  another.

## Readback and permission gates

Generate fresh critical-permission evidence for the exact read-only ERPNext API
key, then reconcile both systems:

```bash
PYTHONPATH=src .venv/bin/python -m operion_etl reconcile-identities \
  --identity-map reports/enterprise/e2/<run-id>/identity_map.csv \
  --output reports/enterprise/e2/<run-id>/identity_map.reconciled.csv \
  --report reports/enterprise/e2/<run-id>/identity-readback.json \
  --target twenty --target erpnext \
  --erpnext-permission-evidence \
    reports/enterprise/e2/<run-id>/erpnext-critical-readonly.json
```

The accepted 2026-09-19 run matched 94/94 ERPNext identities and 39/39 Twenty
identities, with no missing or unexpected records. Its permission evidence shows
all six critical write capabilities denied on all eight protected DocTypes.

Configure the MCP reader with independently measured source timestamps. The
legacy single timestamp remains supported, but the two-source form makes snapshot
skew visible:

```bash
OPERION_CANONICAL_DIR=data/canonical/operion-e2-demo-v1 \
OPERION_IDENTITY_MAP=reports/enterprise/e2/<run-id>/identity_map.reconciled.csv \
OPERION_CUSTOMER_IDS=operion:e2:organization:customer:ambiguous-a,operion:e2:organization:customer:ambiguous-b \
OPERION_TWENTY_OBSERVED_AT=<ISO-8601-Twenty-readback-time> \
OPERION_ERPNEXT_OBSERVED_AT=<ISO-8601-ERPNext-readback-time> \
OPERION_MAX_SNAPSHOT_SKEW_SECONDS=300 \
operion-mcp
```

Customer overview returns both source timestamps and `snapshot_skew_seconds`; it
adds `source_snapshot_skew` when the threshold is exceeded. Fulfillment freshness
depends only on the ERPNext timestamp because Twenty does not contribute stock.

Run the 15 cases in `evaluations/e2/cases.json` three times each during E2. Data
preparation is complete when the seed is ID-stable, identity and permission gates
pass, the MCP exposes exactly two read-only tools, and F01–F06 resolve respectively
to satisfiable, satisfiable, shortfall, shortfall, satisfiable, and
insufficient-information.
