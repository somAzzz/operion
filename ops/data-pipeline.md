# WWI download and ETL runbook

Requirements: Python 3.11+, Docker, and an isolated SQL Server Developer/Enterprise
container with `sqlcmd` and `MSSQL_SA_PASSWORD` set inside it. The default container
name is `enterprise-demo-mssql`.

```bash
PYTHONPATH=src python3 -m operion_etl download-wwi
scripts/restore_wwi.sh data/raw/wwi/<snapshot>/WideWorldImporters-Full.bak
PYTHONPATH=src python3 -m operion_etl run \
  --snapshot data/raw/wwi/<snapshot> \
  --batch-id <unique-batch-id>
```

The downloader never overwrites a snapshot and verifies an existing snapshot
against its manifest. The ETL likewise refuses to overwrite any existing output
directory. A deliberate rerun therefore uses a new batch ID; before loading,
the loader must query targets by `canonical_id`/Operion source key and update the
identity map only after target readback.

Successful ETL evidence is in `reports/<batch-id>/run_manifest.json`. Validation
errors use `data/quarantine/<batch-id>/errors.csv`. Mapping-stage exports are under
`data/exports`; they are not proof of import.

Before a Twenty import, validate the Company and People files together:

```bash
PYTHONPATH=src python3 -m operion_etl validate-twenty \
  --companies data/exports/twenty/<batch-id>/companies.csv \
  --people data/exports/twenty/<batch-id>/people.csv \
  --report reports/<batch-id>/twenty_preimport_validation.json
```

The validator rejects non-canonical or duplicate normalized domains, missing or
duplicate WWI external IDs, nonblank target IDs, missing names, and People company
relations that cannot resolve in the Company file.

Before importing ERPNext files, create Fiscal Year `2016` and add the following
Data custom fields (unique where supported): `Operion Source Key` on Customer,
Supplier, Item, Contact, Sales Order, Sales Order Item, Purchase Order, and Purchase
Order Item; `WWI Source Status` on Sales Order and Purchase Order; and `WWI Supplier
Reference` on Purchase Order. The target already needs Company `AI Demo GmbH`, UOM
`Unit`, customer group `Commercial`, supplier group `All Supplier Groups`, item group
`Products`, territory `Rest Of The World`, and the standard EUR buying/selling price
lists.

Validate the six ERPNext files together:

```bash
PYTHONPATH=src python3 -m operion_etl validate-erpnext \
  --directory data/exports/erpnext/<batch-id> \
  --report reports/<batch-id>/erpnext_preimport_validation.json
```

Import in this order: `customers.csv`, `suppliers.csv`, `items.csv`, `contacts.csv`,
`sales_orders.csv`, then `purchase_orders.csv`. Choose **Insert New Records** and do
not map the blank native `ID` column. Parent orders and their Items child rows are in
the same file; rows after the first child deliberately leave all parent columns
blank. Purchase Orders contain only positive, unreceived open commitments.

The WWI source amount columns do not identify a source currency. For this demo batch,
numeric amounts are intentionally preserved and mapped to the target company's EUR
currency with exchange rate 1; this is a mapping assumption, not a currency
conversion.

After `TWENTY_API_KEY` is present in `.env`, Companies can be loaded idempotently
and read back from `/rest/companies`. The command writes real Twenty UUIDs into the
batch identity map:

```bash
PYTHONPATH=src python3 -m operion_etl load-twenty-companies \
  --companies data/exports/twenty/<batch-id>/companies.csv \
  --people data/exports/twenty/<batch-id>/people.csv \
  --identity-map reports/<batch-id>/identity_map.csv \
  --readback reports/<batch-id>/twenty_companies_readback.json
```

Import People only after Companies. Map `Company WWI External ID` to the Company
relation and select the Company's unique `WWI External ID` as the matching field.
The loader uses supported APIs and never changes Twenty's database indexes.
