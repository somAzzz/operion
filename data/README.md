# Data storage rules

WWI download and minimum ETL are implemented. Actual snapshots and generated artifacts remain local under `.gitignore`. See `ops/data-pipeline.md` for reproducible commands and rerun constraints.

| Directory | Purpose |
| --- | --- |
| raw/wwi | WWI backup and source manifest |
| raw/adventureworks | AdventureWorks backup and source manifest |
| raw/ema | EMA JSON snapshots |
| raw/openfda | Bounded responses and query metadata |
| staging | Optional intermediates; not required initially |
| canonical | Unified business records |
| exports/erpnext | ERPNext import batches |
| exports/twenty | Twenty import batches |
| quarantine | Simple error artifacts; full review workflow deferred |

Use a separate snapshot directory per acquisition, such as `source/UTC-time-or-batch/`. Never overwrite raw snapshots.

Source manifests record URL, retrieval time, version, coverage period, license/terms, size, and checksum. API manifests also retain credential-free endpoint/query parameters, pagination scope, and data-update time.

Each load records source batch, model/mapping and target versions, counts, failures, and reconciliation. Explicitly classify real, public-sample, and simulated data.

Data and run results normally stay outside version control. Reusable nonsensitive models, mappings, contracts, and evaluation cases belong in their corresponding repository directories.

`canonical/demo-v1/` is an exception: the fixed-seed fictional `DEMO` dataset and initial empty-target-ID map are versioned. Actual readback IDs/reports stay in separate ignored run directories.

`canonical/demo-wwi-v1/` is another exception: deterministic versioned IDs and complete-order selection derive from a SHA-256-pinned WWI v1 public sample. Preserve `wwi:*` source keys and `data_class=public_sample`. Its committed map has empty target IDs; actual target readback is not committed.

## Minimum first-version requirements

Raw → Canonical → Target Mapping → Load is sufficient, with validation/readback embedded. Directories are archive locations, not a requirement for multiple services.

Preserve entity type, source system/ID, both target IDs, per-target load state, and errors. Run manifests record batch, time, rule version, and counts, with errors linked to source records. Confirm existing effects before rerunning to avoid duplicates.

Fulfillment demos pin business date/scenario and retain remaining sales/purchase quantities, inbound dates, warehouse stock/reservation definitions, promise, and transport rules. Simulations preserve derivation and labels without overwriting historical inputs. Never mix historical orders, differently timed inventory, and today's date.

Actual native state must support the conclusion: draft orders are not active open orders, and imported Items do not establish available stock. Prepare needed states through supported isolated business operations and verify by readback.
