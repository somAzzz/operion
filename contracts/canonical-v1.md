# Canonical data contract v1

The WWI pipeline writes one immutable batch beneath `data/canonical/<batch-id>/`.
Every real source record has a namespaced `canonical_id`, `source_system=wwi`, a
stable `source_id`, and `data_class=public_sample`.

| File | Grain | Required relations |
|---|---|---|
| `organizations.csv` | customer or supplier organization | role-specific canonical key |
| `contacts.csv` | person | stable WWI PersonID; optional `company_canonical_id` |
| `products.csv` | stock item | supplier source ID and unit conversion |
| `sales_orders.csv` | sales order header | customer and contact keys |
| `sales_order_lines.csv` | sales order line | sales order and product keys |
| `purchase_orders.csv` | purchase order header | supplier and contact keys |
| `purchase_order_lines.csv` | purchase order line | purchase order and product keys |
| `fulfillment_scenarios.csv` | deterministic demo case | product and source-line derivation key |

Quantities in canonical sales lines use the source unit package. Purchase
quantities are converted from outer packages to the product unit package using
`QuantityPerOuter`, while the source outer quantity and conversion factor remain
visible. Monetary values are tax-exclusive and rounded to two decimals.

The six fulfillment cases are simulated overlays derived from public WWI lines.
They use a fixed historical business date, are explicitly marked `simulated`, and
do not modify or impersonate the historical orders or inventory.

The separately versioned `interview-demo-v1` batch uses
`operion:demo:interview-v1:*` keys and contains only explicitly simulated DEMO
records. Its rows add `dataset_version`, `business_date`, and `seed`; order rows
also carry native `docstatus`, source/business status, EUR currency, and a
tax-exclusive net total. `source_observed_at` is deliberately null in the dataset
manifest: runtime observation time must come from an actual snapshot/readback and
must never be invented by the generator.

The separately versioned `interview-wwi-v1` batch uses the same extended CSV
shape and demonstration scale, but every business record is an unmodified
selection from the pinned WWI v1 public sample. It retains stable `wwi:*` keys,
`data_class=public_sample`, source dates and source statuses. `docstatus` is blank
because WWI has no ERPNext-native document state. USD is an explicit dataset-level
assumption because WWI v1 order rows do not contain a currency code; it is not
presented as a source column. The manifest pins the source backup SHA-256, source
profile, selection IDs, and extraction rule.

`reports/<batch-id>/identity_map.csv` permits one canonical record to have rows
for multiple targets. A blank `target_id` with `load_status=pending` means the
mapping exists but no target write or readback has occurred.
`load_status=not_applicable` means the deterministic export rules intentionally
excluded the record (for example, an order line with no open commitment); it is
preserved for lineage but is not counted as a missing target during reconciliation.

For Twenty, `canonical_id` is exported as the unique `WWI External ID`. Website
domains remain business attributes: a domain is emitted only when its normalized
host is unique within the batch. People relations use `company_canonical_id` and
resolve against the Company's `WWI External ID`, never against a shared domain.
