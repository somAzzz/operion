# WWI demo dataset v1 runbook

`demo-wwi-v1` is a second, independent demo dataset. It keeps the same
demonstration scale as `demo-v1`—10 customers, 5 suppliers, 20 contacts,
12 products, 30 sales orders, and 15 purchase orders—but extracts complete source
records from the pinned Wide World Importers v1 public sample. It does not replace
or blend with the simulated dataset.

## Source and deterministic selection

The prepare command requires the checked source manifest SHA-256 and verifies the
restored database profile before extraction. Customer, supplier, and product IDs
are versioned in code. Sales orders are selected per customer by descending WWI
OrderID only when the complete order has 1–4 lines and every line references one
of the 12 selected products. Purchase orders use the latest 15 records satisfying
the same complete-order rule. No order is truncated to fit the target size.

```bash
scripts/restore_wwi.sh \
  data/raw/wwi/20260912T000000Z/WideWorldImporters-Full.bak

.venv/bin/operion-etl prepare-demo-wwi \
  --source-manifest data/raw/wwi/20260912T000000Z/source_manifest.json \
  --output-directory data/canonical/demo-wwi-v1 \
  --identity-map reports/demo-wwi-v1/identity_map.csv \
  --container enterprise-demo-mssql

.venv/bin/operion-etl validate-demo-wwi
```

The generated manifest records the source SHA-256/profile, exact selections,
business date, EUR demo denomination, counts, and identity-row count. Re-running against
the pinned database produces byte-identical files.

## Dry-run and guarded apply

Dry-run is the default and performs no target writes:

```bash
.venv/bin/operion-etl provision-demo-wwi
```

The explicit `--apply` path reuses all safeguards in
[`demo-data.md`](demo-data.md): dedicated untracked admin
credentials, isolated instance attestation, verified backup and restore command,
and disabled external effects. It creates only missing masters and draft orders,
never submits orders, and updates a copied run-specific identity map only after
target IDs are returned.

Mapping revision `demo-wwi-v1.2` denominates all WWI demo prices and amounts
in EUR and preserves source numeric values. WWI does not supply a currency code.

The direct Web profile links each authorized sales order to its ERPNext draft,
Twenty company, and matching order contact. The pinned order set remains available
for offline regressions. To import the ten customers and their 1,197 complete sales
orders into the local demo targets, run the following from the repository root.
The importer reads WWI and verifies each document and line using read-only target
credentials. ERPNext must allow multiple sales orders against a customer purchase order because the WWI customer reference can recur. The import retains that reference on every order. New stock items keep their WWI package unit (Each maps to Unit), and historical drafts use the corresponding company fiscal year. Only the separate provisioning command accesses write credentials.

```bash
PYTHONPATH=src .venv/bin/python scripts/import_wwi_order_records.py --apply
PYTHONPATH=src .venv/bin/python scripts/import_wwi_order_records.py
```

For the separate dependency-closed selection workflow:

```bash
mkdir -p reports/demo-wwi-v1/<run-id>
cp reports/demo-wwi-v1/identity_map.csv \
  reports/demo-wwi-v1/<run-id>/identity_map.prepared.csv

.venv/bin/operion-etl provision-demo-wwi \
  --identity-map reports/demo-wwi-v1/<run-id>/identity_map.prepared.csv \
  --selection-plan config/demo/wwi-first-batch-selection.json \
  --apply --admin-env /absolute/path/to/demo-wwi-admin.env
```

`--selection-plan` accepts sales- and purchase-order canonical IDs only. The
loader expands them to complete lines and the exact customer, supplier,
contacts, and products they depend on; unknown IDs and empty selections fail
closed. It never truncates an order.

For snapshot queries, set `OPERION_CANONICAL_DIR` and `OPERION_IDENTITY_MAP` to
the WWI v1 paths and authorize the canonical customer/supplier IDs listed in
`organizations.csv`. Keep provisioning credentials out of Agent, MCP, browser,
and web processes.
