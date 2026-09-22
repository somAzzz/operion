# WWI interview dataset v1 runbook

`interview-wwi-v1` is a second, independent interview dataset. It keeps the same
demonstration scale as `interview-demo-v1`—10 customers, 5 suppliers, 20 contacts,
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

.venv/bin/operion-etl prepare-interview-wwi \
  --source-manifest data/raw/wwi/20260912T000000Z/source_manifest.json \
  --output-directory data/canonical/interview-wwi-v1 \
  --identity-map reports/interview-wwi-v1/identity_map.csv \
  --container enterprise-demo-mssql

.venv/bin/operion-etl validate-interview-wwi
```

The generated manifest records the source SHA-256/profile, exact selections,
business date, USD assumption, counts, and identity-row count. Re-running against
the pinned database produces byte-identical files.

## Dry-run and guarded apply

Dry-run is the default and performs no target writes:

```bash
.venv/bin/operion-etl provision-interview-wwi
```

The explicit `--apply` path reuses all safeguards in
[`interview-demo-data.md`](interview-demo-data.md): dedicated untracked admin
credentials, isolated instance attestation, verified backup and restore command,
and disabled external effects. It creates only missing masters and draft orders,
never submits orders, and updates a copied run-specific identity map only after
target IDs are returned.

WWI rows use USD as a documented dataset assumption. If the target company base
currency is EUR, the admin environment must also contain a reviewed positive
`OPERION_DEMO_EXCHANGE_RATE_USD_TO_EUR`; the apply path fails closed without it.

```bash
mkdir -p reports/interview-wwi-v1/<run-id>
cp reports/interview-wwi-v1/identity_map.csv \
  reports/interview-wwi-v1/<run-id>/identity_map.prepared.csv

.venv/bin/operion-etl provision-interview-wwi \
  --identity-map reports/interview-wwi-v1/<run-id>/identity_map.prepared.csv \
  --selection-plan config/interview/wwi-first-batch-selection.json \
  --apply --admin-env /absolute/path/to/interview-wwi-admin.env
```

`--selection-plan` accepts sales- and purchase-order canonical IDs only. The
loader expands them to complete lines and the exact customer, supplier,
contacts, and products they depend on; unknown IDs and empty selections fail
closed. It never truncates an order.

For snapshot queries, set `OPERION_CANONICAL_DIR` and `OPERION_IDENTITY_MAP` to
the WWI v1 paths and authorize the canonical customer/supplier IDs listed in
`organizations.csv`. Keep provisioning credentials out of Agent, MCP, browser,
and web processes.
