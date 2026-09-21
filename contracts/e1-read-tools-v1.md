# E1 read-tool contract v1

This contract exposes ten business operations and no generic data, URL, GraphQL,
SQL, mutation, or permission-management primitive. Caller identity is translated
to `AccessScope` by the server. A caller cannot provide a role, token, company,
customer scope, source path, or target address as a tool argument.

## `get_customer_portfolio_summary`

- Purpose: count customers and summarize order coverage within the caller's
  server-defined customer scope.
- Input: optional constant `customer="*"`, meaning every customer already
  authorized by the server. Company and customer scope cannot be supplied by the
  caller.
- Output: authorized customer count, customers with orders, open order count,
  explicit `authorized_customers` scope, observation times, sources, missing
  scoped IDs, and warnings.
- Authorization: only canonical customer IDs present in the server-defined scope
  contribute to any aggregate. It is not an unrestricted company-wide count.
- Side effects: none. The result is derived from the immutable canonical batch.

## Customer and sales-order queries

### `search_customers(query, limit, cursor)`

- Partial, case-insensitive display-name search within server-defined customer IDs.
- Empty query lists the first authorized page. Default 10, maximum 50.
- Results sort by normalized name then canonical ID and return an opaque cursor,
  `has_more`, `truncated`, page count, and no fabricated total count.

### `get_customer_overview`

- Purpose: resolve one customer by canonical ID or exact case-insensitive name and
  return its allowlisted contacts and recent sales orders.
- Input: `customer` (required string), `max_orders` (integer, 1–50; default 20).
- Authorization: the resolved canonical customer ID must be in the server-defined
  scope. Name collisions return candidates and require clarification.
- Output: contract version, operating company, customer IDs, allowlisted contact
  names/IDs, recent order IDs/dates/status, `observed_at`, sources, missing fields,
  warnings, and pagination indication.
- Excluded fields: email, phone, credit limit, payment terms, notes, arbitrary
  custom fields, and all source fields not explicitly constructed by the service.
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
- `draft` means native `docstatus=0`; `confirmed_open` means `docstatus=1` plus
  `business_status=to_deliver`. Source status remains separately visible.

## Supplier and purchase-order queries

`search_suppliers`, `get_supplier_overview`, `list_purchase_orders`, and
`get_purchase_order` mirror the customer contracts but use an independent
server-defined supplier scope. `confirmed_open` for purchases means native
`docstatus=1` plus `business_status=to_receive`; customer scope cannot grant
supplier access.

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
