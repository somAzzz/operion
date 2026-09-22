# E1 read-tool contract v1

Historical E1 acceptance contract. Current customer and supplier contact fields are defined in [Contact overviews v2](contact-overviews-v2.md).

The current MCP interface exposes fifteen read-only business operations and no generic data, URL, GraphQL,
SQL, mutation, or permission-management primitive. Caller identity is translated
to `AccessScope` by the server. A caller cannot provide a role, token, company,
customer scope, source path, or target address as a tool argument.

## `get_customer_portfolio_summary`

- Purpose: count customers and summarize order coverage within the caller's
  server-defined customer scope.
- Input: optional constant `customer="*"`, meaning every customer already
  authorized by the server. Company and customer scope cannot be supplied by the
  caller.
- Output: authorized customer count, customers with orders, total sales order
  count, open order count,
  explicit `authorized_customers` scope, observation times, sources, missing
  scoped IDs, and warnings.
- Authorization: only canonical customer IDs present in the server-defined scope
  contribute to any aggregate. It is not an unrestricted company-wide count.
- Side effects: none. The result is derived from the immutable canonical batch.

## Deterministic resolution and complete-scope aggregation

### `get_customer_order_distribution(customer="*")`

- Computes every authorized customer's sales-order count server-side, including
  customers with zero orders. Its `completeness.status` is `complete` when all
  scoped customer IDs are present in the current dataset, otherwise `partial`.
- `full_source_history=undetermined` prevents a zero count in the sample from
  becoming a claim about all historical WWI orders.

### `get_organization_orders(query, relationship, limit)`

- Resolves customer, supplier, or either relationship inside the caller's scope.
  It returns `resolved`, `ambiguous`, `not_found`, or `denied` without asking
  the model to choose a relationship or same-name entity.
- A resolved result includes unique canonical order IDs, total order count, and
  `complete` or `partial` coverage of the current authorized dataset.

## Contact discovery

### `search_contacts(query, limit, cursor)`

- Searches contact names linked to server-authorized customers or suppliers.
- Returns contact and organization IDs, relationship role, record source,
  identity-map status, and pagination. It does not return email or phone; use
  the corresponding scoped overview to verify those fields.
- A pending identity-map row remains `pending` even when its target ID is blank;
  an empty ID alone does not establish an unmatched identity.
- Snapshot results identify the WWI canonical batch as their source, omit
  live query-system labels, and report `cross_system_verification.status` as
  `not_verified` with reason `snapshot_only`. Target IDs describe mappings,
  not reads.

### `get_contact_by_name(name)`

- Resolves exactly one person linked to an authorized organization. Ambiguous
  names return candidates; absent or out-of-scope people are not exposed.
- Returns each email/phone field with a deterministic state (`present`,
  `explicit_empty`, or `not_exposed`), value, record source, data origin, and
  target identity-map status. No model-side organization matching is required.

## Customer and sales-order queries

### `get_customer_order_context(customer_query, order_id, max_orders)`

- Reads an authorized sales order, follows its customer ID, and verifies that
  the resulting customer's name contains the requested customer query.
- Returns the verified customer overview and order detail together. A name
  mismatch fails closed; the model cannot select a same-name customer itself.

### `search_customers(query, limit, cursor)`

- Partial, case-insensitive display-name search within server-defined customer IDs.
- Empty query lists the first authorized page. Default 10, maximum 50.
- Results sort by normalized name then canonical ID and return an opaque cursor,
  `has_more`, `truncated`, page count, and no fabricated total count.

### `get_customer_overview`

- Purpose: resolve one customer by canonical ID, numeric WWI source ID, or exact case-insensitive name and
  return its allowlisted contacts and recent sales orders.
- Input: `customer` (required string), `max_orders` (integer, 1–50; default 20).
- Authorization: the resolved canonical customer ID must be in the server-defined
  scope. Name collisions return candidates and require clarification.
- Output: contract version, operating company, customer IDs, allowlisted contact
  names/IDs, recent order IDs/dates/status, `observed_at`, sources, missing fields,
  warnings, and pagination indication.
- Contact email and phone are returned only with explicit field state and source
  evidence. Credit limit, payment terms, notes, arbitrary custom fields, and all
  fields not explicitly constructed by the service remain excluded.
- Errors: `not_found`, `ambiguous_customer`, `scope_denied`,
  `invalid_business_input`, or `source_unavailable`. Empty data is not substituted
  for a source error.
- Side effects: none. The repository has no create/update/delete/submit/cancel/amend
  operation and the MCP annotation declares read-only, idempotent, closed-world use.

### `list_sales_orders(...)` and `get_sales_order(order_id)`

- List filters are optional `customer_id`, ISO date bounds, native/business
  `status`, `limit`, and opaque `cursor`. They cannot carry a field name, URL,
  query language, or target method.
- Detail returns only the authorized order and allowlisted item, quantity, UOM,
  tax-exclusive unit rate/amount, currency, and delivery date fields.
- Detail accepts a canonical ID, mapped ERPNext target ID, or numeric WWI
  `source_id` for an authorized sales order. Ambiguous IDs require a canonical ID.
- `draft` means native `docstatus=0`; `confirmed_open` means `docstatus=1` plus
  `business_status=to_deliver`. Source status remains separately visible.
  Structured `status_interpretation` leaves confirmation `unknown` when native
  docstatus is absent. Sales lines return `delivery_state=unknown` when the
  delivered quantity is absent; picked quantity never substitutes for delivery.
- Lists return filtered `total_count` and `completeness.status` separately from
  page count; overview results similarly distinguish zero orders from a partial
  recent-order page.

## Supplier and purchase-order queries

`search_suppliers`, `get_supplier_overview`, `list_purchase_orders`, and
`get_purchase_order` mirror the customer contracts but use an independent
server-defined supplier scope. `confirmed_open` for purchases means native
`docstatus=1` plus `business_status=to_receive`; customer scope cannot grant
supplier access. Purchase-order detail accepts the same ID forms for an
authorized purchase order, including numeric WWI `source_id`.

## `check_fulfillment`

- Purpose: evaluate one frozen `fulfillment-v1` scenario without model arithmetic.
- Input: `case_id` (required string); no caller-supplied quantities or source path.
- Rules: remaining quantity is recomputed; other-order reservations are deducted
  once; only unallocated inbound arriving by the `ship_by` promise date is usable;
  missing inbound date or stale supporting data yields `insufficient_information`.
- Output: one of `satisfiable`, `shortfall`, or `insufficient_information`, plus all
  input quantities, recomputed quantities, promise scope/date, warehouse, item/UOM,
  assumptions, missing fields, data class, source identifiers, and observation time.
- Errors: `not_found`, `invalid_business_input`, or `source_unavailable`.
- Side effects: none; same frozen input and rule version produce the same result.

## Limits and source boundary

Snapshot mode reads one immutable canonical batch and a verified identity map and
requires explicit ISO-8601 observation times. Live mode must be explicitly selected
and uses only the restricted Twenty/ERPNext GET adapters; a live failure returns
`source_unavailable` and never falls back to snapshot data. Freshness is recomputed
on every call. Both modes return at most 50 records and apply authorization inside
every service method. ERPNext identity reconciliation is an operator-only GET client gated by
API-key-bound evidence for Customer, Supplier, Item, Sales Order, Purchase Order,
Warehouse, Bin, and UOM. Contact and ToDo are explicit permission exceptions and
are not represented as proof that the ERPNext credential is globally read-only.
