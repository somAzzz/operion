# E1 read-tool contract v1

This contract exposes two business operations and no generic data, URL, GraphQL,
SQL, mutation, or permission-management primitive. Caller identity is translated
to `AccessScope` by the server. A caller cannot provide a role, token, company,
customer scope, source path, or target address as a tool argument.

## `get_customer_overview`

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

The v1 implementation reads one immutable canonical batch and a verified identity
map. Startup requires an explicit ISO-8601 observation time; it returns at most 50
orders and performs no outbound request from an MCP tool. ERPNext identity
reconciliation is an operator-only GET client gated by
API-key-bound evidence for Customer, Supplier, Item, Sales Order, Purchase Order,
Warehouse, Bin, and UOM. Contact and ToDo are explicit permission exceptions and
are not represented as proof that the ERPNext credential is globally read-only.
