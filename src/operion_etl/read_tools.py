from __future__ import annotations

import base64
import binascii
import csv
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, ClassVar

from .identity_readback import ERPNextReadClient, TwentyReadClient


class ReadToolError(RuntimeError):
    code = "read_tool_error"


class NotFoundError(ReadToolError):
    code = "not_found"


class AmbiguousCustomerError(ReadToolError):
    code = "ambiguous_customer"

    def __init__(self, candidates: list[dict[str, str]]) -> None:
        super().__init__("customer name is ambiguous")
        self.candidates = candidates


class AmbiguousSupplierError(ReadToolError):
    code = "ambiguous_supplier"

    def __init__(self, candidates: list[dict[str, str]]) -> None:
        super().__init__("supplier name is ambiguous")
        self.candidates = candidates


class ScopeDeniedError(ReadToolError):
    code = "scope_denied"


class SourceUnavailableError(ReadToolError):
    code = "source_unavailable"


class InvalidBusinessInputError(ReadToolError):
    code = "invalid_business_input"


@dataclass(frozen=True)
class AccessScope:
    operating_company: str
    customer_ids: frozenset[str]
    supplier_ids: frozenset[str] = frozenset()

    def allows_customer(self, canonical_id: str) -> bool:
        return canonical_id in self.customer_ids

    def allows_supplier(self, canonical_id: str) -> bool:
        return canonical_id in self.supplier_ids


def _cursor_encode(key: tuple[str, str]) -> str:
    payload = json.dumps(key, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _cursor_decode(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(value + padding))
        if not isinstance(decoded, list) or len(decoded) != 2:
            raise ValueError
        return str(decoded[0]), str(decoded[1])
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as error:
        raise InvalidBusinessInputError("cursor is invalid") from error


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except OSError as error:
        raise SourceUnavailableError(
            f"source file is unavailable: {path.name}"
        ) from error


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise InvalidBusinessInputError(f"{field} must be numeric") from error
    if result < 0:
        raise InvalidBusinessInputError(f"{field} must not be negative")
    return result


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidBusinessInputError(
            "observed_at must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class CanonicalRepository:
    """Allowlisted reader for one immutable public-sample canonical batch."""

    MAX_ORDERS = 50
    DEFAULT_PAGE_SIZE = 10
    FILES: ClassVar[set[str]] = {
        "organizations",
        "contacts",
        "sales_orders",
        "sales_order_lines",
        "purchase_orders",
        "purchase_order_lines",
        "products",
        "fulfillment_scenarios",
    }

    def __init__(
        self,
        directory: Path,
        identity_map: Path | None = None,
        observed_at: str | None = None,
        twenty_observed_at: str | None = None,
        erpnext_observed_at: str | None = None,
        stale_after_seconds: int = 3600,
        max_snapshot_skew_seconds: int = 300,
        data_mode: str = "snapshot",
    ) -> None:
        if data_mode not in {"snapshot", "live"}:
            raise InvalidBusinessInputError("data_mode must be snapshot or live")
        self.directory = directory
        self.data_mode = data_mode
        self.stale_after_seconds = stale_after_seconds
        fallback_observed_at = observed_at or datetime.now(UTC).isoformat()
        self.source_observed_at = {
            "twenty": twenty_observed_at or fallback_observed_at,
            "erpnext": erpnext_observed_at or fallback_observed_at,
        }
        observed = {
            source: _timestamp(value)
            for source, value in self.source_observed_at.items()
        }
        oldest_observed = min(observed.values())
        self.observed_at = oldest_observed.isoformat()
        self._observed_datetimes = observed
        self.snapshot_skew_seconds = round(
            abs((observed["twenty"] - observed["erpnext"]).total_seconds()), 3
        )
        self.snapshot_skew = self.snapshot_skew_seconds > max_snapshot_skew_seconds
        self.data = {name: _read_csv(directory / f"{name}.csv") for name in self.FILES}
        self.target_ids: dict[tuple[str, str], str] = {}
        if identity_map is not None:
            for row in _read_csv(identity_map):
                if row.get("target_id"):
                    self.target_ids[(row["target_system"], row["canonical_id"])] = row[
                        "target_id"
                    ]

    @property
    def source_stale_by_system(self) -> dict[str, bool]:
        now = datetime.now(UTC)
        return {
            source: (now - timestamp).total_seconds() > self.stale_after_seconds
            for source, timestamp in self._observed_datetimes.items()
        }

    @property
    def source_stale(self) -> bool:
        return any(self.source_stale_by_system.values())

    def _warnings(self, sources: list[str]) -> list[str]:
        warnings: list[str] = []
        stale_by_system = self.source_stale_by_system
        if any(stale_by_system[source] for source in sources):
            warnings.append("source_stale")
        if set(sources) >= {"twenty", "erpnext"} and self.snapshot_skew:
            warnings.append("source_snapshot_skew")
        if self.data_mode == "snapshot":
            warnings.append("snapshot_not_live")
        return warnings

    def _metadata(self, *, source_system: list[str]) -> dict[str, Any]:
        classes = sorted(
            {
                row.get("data_class", "")
                for name, rows in self.data.items()
                if name != "fulfillment_scenarios"
                for row in rows
                if row.get("data_class")
            }
        )
        observed = {source: self.source_observed_at[source] for source in source_system}
        oldest = min(self._observed_datetimes[source] for source in source_system)
        return {
            "data_mode": self.data_mode,
            "data_class": classes[0] if len(classes) == 1 else classes,
            "source_system": source_system,
            "observed_at": oldest.isoformat(),
            "source_observed_at": observed,
            "snapshot_skew_seconds": (
                self.snapshot_skew_seconds
                if set(source_system) >= {"twenty", "erpnext"}
                else 0
            ),
            "sources": ["canonical-v1", *source_system],
            "warnings": self._warnings(source_system),
        }

    def _page(
        self,
        rows: list[dict[str, Any]],
        *,
        limit: int,
        cursor: str | None,
        key_fields: tuple[str, str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not 1 <= limit <= self.MAX_ORDERS:
            raise InvalidBusinessInputError("limit must be between 1 and 50")
        after = _cursor_decode(cursor)
        keyed = [
            ((str(row[key_fields[0]]).casefold(), str(row[key_fields[1]])), row)
            for row in rows
        ]
        keyed.sort(key=lambda item: item[0])
        if after is not None:
            normalized = (after[0].casefold(), after[1])
            keyed = [item for item in keyed if item[0] > normalized]
        page = keyed[: limit + 1]
        has_more = len(page) > limit
        page = page[:limit]
        next_cursor = _cursor_encode(page[-1][0]) if has_more and page else None
        return [row for _, row in page], {
            "limit": limit,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "truncated": has_more,
            "sort": f"{key_fields[0]} asc, {key_fields[1]} asc",
            "page_count": len(page),
            "total_count": None,
        }

    def customer_portfolio_summary(self, scope: AccessScope) -> dict[str, Any]:
        """Summarize customers visible through the server-defined access scope."""
        customers = [
            row
            for row in self.data["organizations"]
            if row["roles"] == "customer" and scope.allows_customer(row["canonical_id"])
        ]
        customer_ids = {row["canonical_id"] for row in customers}
        orders = [
            row
            for row in self.data["sales_orders"]
            if row["customer_canonical_id"] in customer_ids
        ]
        customers_with_orders = {row["customer_canonical_id"] for row in orders}
        missing_customer_ids = sorted(scope.customer_ids - customer_ids)
        return {
            "contract_version": "customer-portfolio-v1",
            "operating_company": scope.operating_company,
            "scope": "authorized_customers",
            "customer_count": len(customers),
            "customers_with_orders": len(customers_with_orders),
            "open_order_count": sum(
                row["source_status"].strip().casefold() == "open"
                or self._status_matches(row, "confirmed_open", "sales")
                for row in orders
            ),
            "missing": [
                f"customer:{customer_id}" for customer_id in missing_customer_ids
            ],
            **self._metadata(source_system=["twenty", "erpnext"]),
        }

    def _resolve_organization(
        self,
        value: str,
        scope: AccessScope,
        role: str,
    ) -> dict[str, str]:
        if not value.strip():
            raise InvalidBusinessInputError(f"{role} is required")
        allowed = scope.allows_customer if role == "customer" else scope.allows_supplier
        organizations = [
            row for row in self.data["organizations"] if row["roles"] == role
        ]
        id_matches = [row for row in organizations if row["canonical_id"] == value]
        if id_matches:
            if not allowed(id_matches[0]["canonical_id"]):
                raise ScopeDeniedError(
                    f"{role} is outside the authorized scope or unavailable"
                )
            return id_matches[0]
        needle = value.strip().casefold()
        matches = [
            row
            for row in organizations
            if row["name"].strip().casefold() == needle and allowed(row["canonical_id"])
        ]
        if not matches:
            raise NotFoundError(f"{role} was not found in the authorized scope")
        if len(matches) > 1:
            candidates = [
                {
                    "canonical_id": row["canonical_id"],
                    "name": row["name"],
                    "city": row.get("city", ""),
                }
                for row in matches
            ]
            if role == "customer":
                raise AmbiguousCustomerError(candidates)
            raise AmbiguousSupplierError(candidates)
        return matches[0]

    def _organization_search(
        self,
        query: str,
        scope: AccessScope,
        role: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        if len(query) > 200:
            raise InvalidBusinessInputError("query must not exceed 200 characters")
        allowed = scope.allows_customer if role == "customer" else scope.allows_supplier
        needle = query.strip().casefold()
        matches = [
            {
                "canonical_id": row["canonical_id"],
                "target_id": self.target_ids.get(
                    (
                        ("twenty" if role == "customer" else "erpnext"),
                        row["canonical_id"],
                    ),
                    "",
                ),
                "name": row["name"],
                "city": row.get("city", ""),
                "country": row.get("country", ""),
                "source_system": row.get("source_system", ""),
                "data_class": row.get("data_class", ""),
            }
            for row in self.data["organizations"]
            if row["roles"] == role
            and allowed(row["canonical_id"])
            and (not needle or needle in row["name"].casefold())
        ]
        page, pagination = self._page(
            matches,
            limit=limit,
            cursor=cursor,
            key_fields=("name", "canonical_id"),
        )
        return {
            "contract_version": f"{role}-search-v1",
            "query": query,
            "results": page,
            "pagination": pagination,
            "missing": [],
            **self._metadata(
                source_system=["twenty"] if role == "customer" else ["erpnext"]
            ),
        }

    def search_customers(
        self,
        query: str,
        scope: AccessScope,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._organization_search(query, scope, "customer", limit, cursor)

    def search_suppliers(
        self,
        query: str,
        scope: AccessScope,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._organization_search(query, scope, "supplier", limit, cursor)

    def customer_overview(
        self,
        customer: str,
        scope: AccessScope,
        max_orders: int = 20,
    ) -> dict[str, Any]:
        if not 1 <= max_orders <= self.MAX_ORDERS:
            raise InvalidBusinessInputError("max_orders must be between 1 and 50")
        organization = self._resolve_organization(customer, scope, "customer")
        canonical_id = organization["canonical_id"]

        contacts = [
            {
                "canonical_id": row["canonical_id"],
                "full_name": row["full_name"],
                "preferred_name": row["preferred_name"],
                "twenty_id": self.target_ids.get(("twenty", row["canonical_id"]), ""),
                "erpnext_id": self.target_ids.get(("erpnext", row["canonical_id"]), ""),
            }
            for row in self.data["contacts"]
            if row["company_canonical_id"] == canonical_id
        ]
        orders = [
            {
                "canonical_id": row["canonical_id"],
                "order_date": row["order_date"],
                "expected_delivery_date": row["expected_delivery_date"],
                "source_status": row["source_status"],
                "docstatus": row.get("docstatus", ""),
                "business_status": row.get("business_status", row["source_status"]),
                "currency": row.get("currency", ""),
                "net_total_ex_tax": row.get("net_total_ex_tax", ""),
                "erpnext_id": self.target_ids.get(("erpnext", row["canonical_id"]), ""),
            }
            for row in self.data["sales_orders"]
            if row["customer_canonical_id"] == canonical_id
        ]
        orders.sort(
            key=lambda row: (row["order_date"], row["canonical_id"]), reverse=True
        )
        return {
            "contract_version": "customer-overview-v1",
            "operating_company": scope.operating_company,
            "customer": {
                "canonical_id": canonical_id,
                "name": organization["name"],
                "twenty_id": self.target_ids.get(("twenty", canonical_id), ""),
                "erpnext_id": self.target_ids.get(("erpnext", canonical_id), ""),
            },
            "contacts": contacts,
            "orders": orders[:max_orders],
            "has_more_orders": len(orders) > max_orders,
            "missing": [],
            **self._metadata(source_system=["twenty", "erpnext"]),
        }

    def supplier_overview(
        self,
        supplier: str,
        scope: AccessScope,
        max_orders: int = 20,
    ) -> dict[str, Any]:
        if not 1 <= max_orders <= self.MAX_ORDERS:
            raise InvalidBusinessInputError("max_orders must be between 1 and 50")
        organization = self._resolve_organization(supplier, scope, "supplier")
        canonical_id = organization["canonical_id"]
        contacts = [
            {
                "canonical_id": row["canonical_id"],
                "full_name": row["full_name"],
                "relationship": row.get("relationship", "supplier contact"),
                "erpnext_id": self.target_ids.get(("erpnext", row["canonical_id"]), ""),
            }
            for row in self.data["contacts"]
            if row["company_canonical_id"] == canonical_id
        ]
        orders = [
            self._purchase_order_summary(row)
            for row in self.data["purchase_orders"]
            if row["supplier_canonical_id"] == canonical_id
        ]
        orders.sort(
            key=lambda row: (row["order_date"], row["canonical_id"]), reverse=True
        )
        return {
            "contract_version": "supplier-overview-v1",
            "operating_company": scope.operating_company,
            "supplier": {
                "canonical_id": canonical_id,
                "name": organization["name"],
                "erpnext_id": self.target_ids.get(("erpnext", canonical_id), ""),
            },
            "contacts": contacts,
            "orders": orders[:max_orders],
            "has_more_orders": len(orders) > max_orders,
            "missing": [],
            **self._metadata(source_system=["erpnext"]),
        }

    def _sales_order_summary(self, row: dict[str, str]) -> dict[str, Any]:
        customer = next(
            (
                item
                for item in self.data["organizations"]
                if item["canonical_id"] == row["customer_canonical_id"]
            ),
            {},
        )
        return {
            "canonical_id": row["canonical_id"],
            "target_id": self.target_ids.get(("erpnext", row["canonical_id"]), ""),
            "customer_id": row["customer_canonical_id"],
            "customer_name": customer.get("name", ""),
            "order_number": row.get("customer_po_number") or row["source_id"],
            "order_date": row["order_date"],
            "expected_delivery_date": row["expected_delivery_date"],
            "currency": row.get("currency", ""),
            "net_total_ex_tax": row.get("net_total_ex_tax", ""),
            "docstatus": row.get("docstatus", ""),
            "business_status": row.get("business_status", row["source_status"]),
            "source_status": row["source_status"],
            "data_class": row.get("data_class", ""),
            "source_system": row.get("source_system", ""),
        }

    def _purchase_order_summary(self, row: dict[str, str]) -> dict[str, Any]:
        supplier = next(
            (
                item
                for item in self.data["organizations"]
                if item["canonical_id"] == row["supplier_canonical_id"]
            ),
            {},
        )
        return {
            "canonical_id": row["canonical_id"],
            "target_id": self.target_ids.get(("erpnext", row["canonical_id"]), ""),
            "supplier_id": row["supplier_canonical_id"],
            "supplier_name": supplier.get("name", ""),
            "order_number": row.get("supplier_reference") or row["source_id"],
            "order_date": row["order_date"],
            "expected_delivery_date": row["expected_delivery_date"],
            "currency": row.get("currency", ""),
            "net_total_ex_tax": row.get("net_total_ex_tax", ""),
            "docstatus": row.get("docstatus", ""),
            "business_status": row.get("business_status", row["source_status"]),
            "source_status": row["source_status"],
            "data_class": row.get("data_class", ""),
            "source_system": row.get("source_system", ""),
        }

    def _validate_dates(self, date_from: str | None, date_to: str | None) -> None:
        try:
            start = date.fromisoformat(date_from) if date_from else None
            end = date.fromisoformat(date_to) if date_to else None
        except ValueError as error:
            raise InvalidBusinessInputError("dates must use YYYY-MM-DD") from error
        if start and end and start > end:
            raise InvalidBusinessInputError("date_from must not be after date_to")

    @staticmethod
    def _status_matches(row: dict[str, str], status: str | None, kind: str) -> bool:
        if not status:
            return True
        raw = row.get("source_status", "").casefold()
        business = row.get("business_status", raw).casefold()
        normalized_business = business.replace(" ", "_").replace("-", "_")
        docstatus = row.get("docstatus", "")
        requested = status.strip().casefold()
        if requested == "draft":
            return docstatus == "0" or normalized_business == "draft"
        if requested == "confirmed_open":
            expected = "to_deliver" if kind == "sales" else "to_receive"
            return docstatus == "1" and normalized_business.startswith(expected)
        if requested in {"undelivered", "unreceived", "unfinished"}:
            expected = "to_deliver" if kind == "sales" else "to_receive"
            return docstatus == "1" and normalized_business.startswith(expected)
        return requested in {raw, business, normalized_business, docstatus}

    def _list_orders(
        self,
        *,
        kind: str,
        organization_id: str | None,
        date_from: str | None,
        date_to: str | None,
        status: str | None,
        limit: int,
        cursor: str | None,
        scope: AccessScope,
    ) -> dict[str, Any]:
        self._validate_dates(date_from, date_to)
        if status is not None and len(status) > 64:
            raise InvalidBusinessInputError("status must not exceed 64 characters")
        if kind == "sales":
            orders = self.data["sales_orders"]
            relation = "customer_canonical_id"
            allows = scope.allows_customer
            summary = self._sales_order_summary
        else:
            orders = self.data["purchase_orders"]
            relation = "supplier_canonical_id"
            allows = scope.allows_supplier
            summary = self._purchase_order_summary
        if organization_id and not allows(organization_id):
            raise ScopeDeniedError(
                f"{kind} order organization is outside the authorized scope or unavailable"
            )
        matches = [
            summary(row)
            for row in orders
            if allows(row[relation])
            and (not organization_id or row[relation] == organization_id)
            and (not date_from or row["order_date"] >= date_from)
            and (not date_to or row["order_date"] <= date_to)
            and self._status_matches(row, status, kind)
        ]
        page, pagination = self._page(
            matches,
            limit=limit,
            cursor=cursor,
            key_fields=("order_date", "canonical_id"),
        )
        return {
            "contract_version": f"{kind}-order-list-v1",
            "orders": page,
            "filters": {
                ("customer_id" if kind == "sales" else "supplier_id"): organization_id,
                "date_from": date_from,
                "date_to": date_to,
                "status": status,
            },
            "status_filter_definition": {
                "draft": "native docstatus=0; not a confirmed open order",
                "confirmed_open": (
                    "native docstatus=1 and business_status=to_deliver"
                    if kind == "sales"
                    else "native docstatus=1 and business_status=to_receive"
                ),
            },
            "pagination": pagination,
            "missing": [],
            **self._metadata(source_system=["erpnext"]),
        }

    def list_sales_orders(
        self,
        scope: AccessScope,
        customer_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._list_orders(
            kind="sales",
            organization_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
            cursor=cursor,
            scope=scope,
        )

    def list_purchase_orders(
        self,
        scope: AccessScope,
        supplier_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._list_orders(
            kind="purchase",
            organization_id=supplier_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
            cursor=cursor,
            scope=scope,
        )

    def _get_order(
        self, order_id: str, scope: AccessScope, kind: str
    ) -> dict[str, Any]:
        if not order_id.strip():
            raise InvalidBusinessInputError("order_id is required")
        if kind == "sales":
            table, line_table = "sales_orders", "sales_order_lines"
            relation, line_relation = (
                "customer_canonical_id",
                "sales_order_canonical_id",
            )
            allows, summary = scope.allows_customer, self._sales_order_summary
        else:
            table, line_table = "purchase_orders", "purchase_order_lines"
            relation, line_relation = (
                "supplier_canonical_id",
                "purchase_order_canonical_id",
            )
            allows, summary = scope.allows_supplier, self._purchase_order_summary
        matches = [
            row
            for row in self.data[table]
            if (
                row["canonical_id"] == order_id
                or self.target_ids.get(("erpnext", row["canonical_id"])) == order_id
            )
            and allows(row[relation])
        ]
        if not matches:
            raise ScopeDeniedError(
                "order is outside the authorized scope or unavailable"
            )
        row = matches[0]
        product_names = {
            item["canonical_id"]: item["name"] for item in self.data["products"]
        }
        lines = []
        for item in self.data[line_table]:
            if item[line_relation] != row["canonical_id"]:
                continue
            if kind == "sales":
                quantity = item["ordered_quantity"]
                uom = item["uom"]
                rate = item["unit_price_ex_tax"]
            else:
                quantity = item["ordered_outers"]
                uom = item["canonical_uom"]
                rate = item["expected_unit_price_each"]
            lines.append(
                {
                    "canonical_id": item["canonical_id"],
                    "target_id": self.target_ids.get(
                        ("erpnext", item["canonical_id"]), ""
                    ),
                    "product_id": item["product_canonical_id"],
                    "product_name": product_names.get(item["product_canonical_id"], ""),
                    "description": item["description"],
                    "quantity": quantity,
                    "uom": uom,
                    "unit_price_ex_tax": rate,
                    "net_amount": item.get("net_amount", ""),
                    "currency": item.get("currency", row.get("currency", "")),
                    "delivery_date": row["expected_delivery_date"],
                }
            )
        return {
            "contract_version": f"{kind}-order-detail-v1",
            "order": summary(row),
            "lines": lines,
            "missing": [],
            **self._metadata(source_system=["erpnext"]),
        }

    def get_sales_order(self, order_id: str, scope: AccessScope) -> dict[str, Any]:
        return self._get_order(order_id, scope, "sales")

    def get_purchase_order(self, order_id: str, scope: AccessScope) -> dict[str, Any]:
        return self._get_order(order_id, scope, "purchase")

    def fulfillment_case(self, case_id: str) -> dict[str, Any]:
        matches = [
            row
            for row in self.data["fulfillment_scenarios"]
            if row["case_id"] == case_id
        ]
        if not matches:
            raise NotFoundError("fulfillment case was not found")
        return evaluate_fulfillment(
            matches[0],
            observed_at=self.source_observed_at["erpnext"],
            source_stale=self.source_stale_by_system["erpnext"],
            source_observed_at={"erpnext": self.source_observed_at["erpnext"]},
        )


class LiveReadRepository(CanonicalRepository):
    """Read-only target adapter with canonical keys as the authorization join."""

    def __init__(
        self,
        directory: Path,
        *,
        identity_map: Path,
        twenty: TwentyReadClient,
        erpnext: ERPNextReadClient,
        stale_after_seconds: int = 3600,
        max_snapshot_skew_seconds: int = 300,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        super().__init__(
            directory,
            identity_map=identity_map,
            twenty_observed_at=now,
            erpnext_observed_at=now,
            stale_after_seconds=stale_after_seconds,
            max_snapshot_skew_seconds=max_snapshot_skew_seconds,
            data_mode="live",
        )
        self.twenty = twenty
        self.erpnext = erpnext
        self._canonical_snapshot = deepcopy(self.data)

    def _mark_observed(self, source: str) -> None:
        observed = datetime.now(UTC)
        self._observed_datetimes[source] = observed
        self.source_observed_at[source] = observed.isoformat()
        oldest = min(self._observed_datetimes.values())
        self.observed_at = oldest.isoformat()
        self.snapshot_skew_seconds = round(
            abs(
                (
                    self._observed_datetimes["twenty"]
                    - self._observed_datetimes["erpnext"]
                ).total_seconds()
            ),
            3,
        )

    def _refresh_twenty(self) -> None:
        try:
            companies = self.twenty.records("companies")
            people = self.twenty.records("people")
        except Exception as error:
            raise SourceUnavailableError("Twenty live source is unavailable") from error
        company_by_key = {str(row.get("wwiExternalId") or ""): row for row in companies}
        person_by_key = {str(row.get("wwiExternalId") or ""): row for row in people}
        organizations: list[dict[str, str]] = []
        for base in self._canonical_snapshot["organizations"]:
            if base["roles"] != "customer":
                organizations.append(dict(base))
                continue
            live = company_by_key.get(base["canonical_id"])
            if not live:
                continue
            row = dict(base)
            row["name"] = str(live.get("name") or base["name"])
            row["source_system"] = "twenty"
            organizations.append(row)
            if live.get("id"):
                self.target_ids[("twenty", base["canonical_id"])] = str(live["id"])
        contacts: list[dict[str, str]] = []
        for base in self._canonical_snapshot["contacts"]:
            if ":supplier:" in base["company_canonical_id"]:
                contacts.append(dict(base))
                continue
            live = person_by_key.get(base["canonical_id"])
            if not live:
                continue
            row = dict(base)
            name = live.get("name") or {}
            full_name = " ".join(
                str(name.get(field) or "") for field in ("firstName", "lastName")
            ).strip()
            row["full_name"] = full_name or base["full_name"]
            row["source_system"] = "twenty"
            contacts.append(row)
            if live.get("id"):
                self.target_ids[("twenty", base["canonical_id"])] = str(live["id"])
        self.data["organizations"] = organizations
        self.data["contacts"] = contacts
        self._mark_observed("twenty")

    def _refresh_erpnext(self) -> None:
        try:
            customers = self.erpnext.records(
                "Customer", ["name", "customer_name", "custom_operion_source_key"]
            )
            suppliers = self.erpnext.records(
                "Supplier", ["name", "supplier_name", "custom_operion_sourcekey"]
            )
            items = self.erpnext.records(
                "Item", ["name", "item_name", "stock_uom", "custom_operion_source_key"]
            )
            contacts = self.erpnext.records(
                "Contact",
                ["name", "first_name", "last_name", "custom_operion_source_key"],
            )
            sales = self.erpnext.records(
                "Sales Order",
                [
                    "name",
                    "customer",
                    "transaction_date",
                    "delivery_date",
                    "status",
                    "docstatus",
                    "currency",
                    "net_total",
                    "po_no",
                    "custom_operion_source_key",
                ],
            )
            purchases = self.erpnext.records(
                "Purchase Order",
                [
                    "name",
                    "supplier",
                    "transaction_date",
                    "schedule_date",
                    "status",
                    "docstatus",
                    "currency",
                    "net_total",
                    "custom_operion_source_key",
                ],
            )
        except Exception as error:
            raise SourceUnavailableError(
                "ERPNext live source is unavailable"
            ) from error

        customer_by_key = {
            str(row.get("custom_operion_source_key") or ""): row for row in customers
        }
        supplier_by_key = {
            str(row.get("custom_operion_sourcekey") or ""): row for row in suppliers
        }
        live_organizations: list[dict[str, str]] = []
        for base in self._canonical_snapshot["organizations"]:
            source = customer_by_key if base["roles"] == "customer" else supplier_by_key
            live = source.get(base["canonical_id"])
            if not live:
                continue
            row = dict(base)
            name_field = (
                "customer_name" if base["roles"] == "customer" else "supplier_name"
            )
            row["name"] = str(live.get(name_field) or base["name"])
            row["source_system"] = "erpnext"
            live_organizations.append(row)
            if live.get("name"):
                self.target_ids[("erpnext", base["canonical_id"])] = str(live["name"])
        self.data["organizations"] = live_organizations

        contact_by_key = {
            str(row.get("custom_operion_source_key") or ""): row for row in contacts
        }
        live_contacts: list[dict[str, str]] = []
        for base in self._canonical_snapshot["contacts"]:
            live = contact_by_key.get(base["canonical_id"])
            if not live:
                continue
            row = dict(base)
            full_name = " ".join(
                str(live.get(field) or "") for field in ("first_name", "last_name")
            ).strip()
            row["full_name"] = full_name or base["full_name"]
            row["source_system"] = "erpnext"
            live_contacts.append(row)
            if live.get("name"):
                self.target_ids[("erpnext", base["canonical_id"])] = str(live["name"])
        self.data["contacts"] = live_contacts

        item_by_key = {
            str(row.get("custom_operion_source_key") or ""): row for row in items
        }
        target_product: dict[str, str] = {}
        live_products: list[dict[str, str]] = []
        for base in self._canonical_snapshot["products"]:
            live = item_by_key.get(base["canonical_id"])
            if not live:
                continue
            row = dict(base)
            row["name"] = str(live.get("item_name") or base["name"])
            row["source_system"] = "erpnext"
            live_products.append(row)
            if live.get("name"):
                target = str(live["name"])
                self.target_ids[("erpnext", base["canonical_id"])] = target
                target_product[target] = base["canonical_id"]
        self.data["products"] = live_products

        def live_orders(
            records: list[dict[str, Any]],
            table: str,
            line_table: str,
            kind: str,
        ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
            base_orders = {
                row["canonical_id"]: row for row in self._canonical_snapshot[table]
            }
            headers: list[dict[str, str]] = []
            lines: list[dict[str, str]] = []
            for live in records:
                canonical_id = str(live.get("custom_operion_source_key") or "")
                base = base_orders.get(canonical_id)
                if not base:
                    continue
                row = dict(base)
                row["source_system"] = "erpnext"
                row["order_date"] = str(
                    live.get("transaction_date") or row["order_date"]
                )
                delivery_field = "delivery_date" if kind == "sales" else "schedule_date"
                row["expected_delivery_date"] = str(
                    live.get(delivery_field) or row["expected_delivery_date"]
                )
                row["source_status"] = str(live.get("status") or "")
                row["business_status"] = row["source_status"]
                row["docstatus"] = str(live.get("docstatus") or 0)
                row["currency"] = str(live.get("currency") or "")
                row["net_total_ex_tax"] = _text(live.get("net_total"))
                headers.append(row)
                target_id = str(live.get("name") or "")
                if target_id:
                    self.target_ids[("erpnext", canonical_id)] = target_id
                detail = self.erpnext.record(
                    "Sales Order" if kind == "sales" else "Purchase Order", target_id
                )
                for position, item in enumerate(detail.get("items", []), 1):
                    line_key_field = (
                        "custom_operion_source_key_items"
                        if kind == "sales"
                        else "custom_operion_source_key"
                    )
                    line_key = str(item.get(line_key_field) or "")
                    if not line_key:
                        line_key = f"{canonical_id}:live-line:{position:03d}"
                    product_id = target_product.get(
                        str(item.get("item_code") or ""), ""
                    )
                    common = {
                        "canonical_id": line_key,
                        "source_system": "erpnext",
                        "source_id": str(item.get("name") or ""),
                        "product_canonical_id": product_id,
                        "description": str(
                            item.get("description") or item.get("item_name") or ""
                        ),
                        "data_class": base.get("data_class", ""),
                        "currency": row["currency"],
                        "net_amount": _text(item.get("amount")),
                    }
                    if kind == "sales":
                        line = {
                            **common,
                            "sales_order_canonical_id": canonical_id,
                            "uom": str(item.get("uom") or ""),
                            "ordered_quantity": _text(item.get("qty")),
                            "delivered_quantity": _text(item.get("delivered_qty")),
                            "open_quantity": str(
                                Decimal(str(item.get("qty") or 0))
                                - Decimal(str(item.get("delivered_qty") or 0))
                            ),
                            "unit_price_ex_tax": _text(item.get("rate")),
                            "tax_rate_percent": "",
                        }
                    else:
                        line = {
                            **common,
                            "purchase_order_canonical_id": canonical_id,
                            "source_uom": str(item.get("uom") or ""),
                            "canonical_uom": str(item.get("uom") or ""),
                            "units_per_outer": "1",
                            "ordered_outers": _text(item.get("qty")),
                            "received_outers": _text(item.get("received_qty")),
                            "open_quantity": str(
                                Decimal(str(item.get("qty") or 0))
                                - Decimal(str(item.get("received_qty") or 0))
                            ),
                            "expected_unit_price_per_outer": _text(item.get("rate")),
                            "expected_unit_price_each": _text(item.get("rate")),
                            "last_receipt_date": "",
                        }
                    lines.append(line)
                    if item.get("name"):
                        self.target_ids[("erpnext", line_key)] = str(item["name"])
            return headers, lines

        self.data["sales_orders"], self.data["sales_order_lines"] = live_orders(
            sales, "sales_orders", "sales_order_lines", "sales"
        )
        self.data["purchase_orders"], self.data["purchase_order_lines"] = live_orders(
            purchases, "purchase_orders", "purchase_order_lines", "purchase"
        )
        self._mark_observed("erpnext")

    def search_customers(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_twenty()
        return super().search_customers(*args, **kwargs)

    def customer_portfolio_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        self._refresh_twenty()
        return super().customer_portfolio_summary(*args, **kwargs)

    def customer_overview(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        self._refresh_twenty()
        return super().customer_overview(*args, **kwargs)

    def search_suppliers(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        return super().search_suppliers(*args, **kwargs)

    def supplier_overview(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        return super().supplier_overview(*args, **kwargs)

    def list_sales_orders(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        return super().list_sales_orders(*args, **kwargs)

    def list_purchase_orders(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        return super().list_purchase_orders(*args, **kwargs)

    def get_sales_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        return super().get_sales_order(*args, **kwargs)

    def get_purchase_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._refresh_erpnext()
        return super().get_purchase_order(*args, **kwargs)


def evaluate_fulfillment(
    scenario: dict[str, Any],
    *,
    observed_at: str,
    source_stale: bool = False,
    source_observed_at: dict[str, str] | None = None,
) -> dict[str, Any]:
    required = {
        "case_id",
        "scenario_version",
        "business_date",
        "promise_scope",
        "promise_date",
        "warehouse",
        "product_canonical_id",
        "uom",
        "ordered_quantity",
        "delivered_quantity",
        "on_hand_quantity",
        "reserved_for_other_orders",
        "unallocated_inbound_quantity",
        "expected_inbound_date",
        "data_class",
    }
    missing_fields = sorted(field for field in required if field not in scenario)
    if missing_fields:
        raise InvalidBusinessInputError(f"missing scenario fields: {missing_fields}")

    ordered = _decimal(scenario["ordered_quantity"], "ordered_quantity")
    delivered = _decimal(scenario["delivered_quantity"], "delivered_quantity")
    if delivered > ordered:
        raise InvalidBusinessInputError("delivered_quantity exceeds ordered_quantity")
    remaining = ordered - delivered
    on_hand = _decimal(scenario["on_hand_quantity"], "on_hand_quantity")
    reserved_other = _decimal(
        scenario["reserved_for_other_orders"], "reserved_for_other_orders"
    )
    inbound = _decimal(
        scenario["unallocated_inbound_quantity"], "unallocated_inbound_quantity"
    )
    available_now = max(on_hand - reserved_other, Decimal(0))
    promise_date = date.fromisoformat(str(scenario["promise_date"]))
    inbound_date_raw = str(scenario.get("expected_inbound_date") or "")
    missing: list[str] = []
    usable_inbound = Decimal(0)
    if inbound > 0:
        if not inbound_date_raw:
            missing.append("expected_inbound_date")
        else:
            inbound_date = date.fromisoformat(inbound_date_raw)
            if inbound_date <= promise_date:
                usable_inbound = inbound

    total_supply = available_now + usable_inbound
    if missing and available_now < remaining:
        result = "insufficient_information"
    elif total_supply >= remaining:
        result = "satisfiable"
    else:
        result = "shortfall"
    if source_stale and result == "satisfiable":
        missing.append("source_freshness")
        result = "insufficient_information"
    quantity_shortfall = max(remaining - total_supply, Decimal(0))
    return {
        "contract_version": "fulfillment-v1",
        "data_mode": "snapshot",
        "warnings": ["frozen_fulfillment_snapshot"],
        "case_id": scenario["case_id"],
        "result": result,
        "business_date": str(scenario["business_date"]),
        "promise_scope": scenario["promise_scope"],
        "promise_date": str(scenario["promise_date"]),
        "warehouse": scenario["warehouse"],
        "product_canonical_id": scenario["product_canonical_id"],
        "uom": scenario["uom"],
        "quantities": {
            "ordered": _number(ordered),
            "delivered": _number(delivered),
            "remaining": _number(remaining),
            "on_hand": _number(on_hand),
            "reserved_for_other_orders": _number(reserved_other),
            "available_now": _number(available_now),
            "unallocated_inbound": _number(inbound),
            "usable_inbound_by_promise": _number(usable_inbound),
            "shortfall": _number(quantity_shortfall),
        },
        "expected_inbound_date": inbound_date_raw or None,
        "missing": missing,
        "assumptions": [
            "single warehouse",
            "reserved_for_other_orders excludes the current order",
            "unallocated inbound is not reused across this result",
            "promise scope is ship_by",
        ],
        "data_class": scenario["data_class"],
        "observed_at": observed_at,
        "source_observed_at": source_observed_at or {"erpnext": observed_at},
        "sources": [
            source
            for source in (
                str(scenario.get("derived_from") or ""),
                str(scenario.get("on_hand_source") or ""),
                str(scenario.get("reservation_source") or ""),
                str(scenario.get("inbound_source") or ""),
                str(scenario.get("fulfillment_source") or ""),
                "fulfillment-v1",
            )
            if source
        ],
    }
