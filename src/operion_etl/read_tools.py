from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, ClassVar


class ReadToolError(RuntimeError):
    code = "read_tool_error"


class NotFoundError(ReadToolError):
    code = "not_found"


class AmbiguousCustomerError(ReadToolError):
    code = "ambiguous_customer"

    def __init__(self, candidates: list[dict[str, str]]) -> None:
        super().__init__("customer name is ambiguous")
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

    def allows_customer(self, canonical_id: str) -> bool:
        return canonical_id in self.customer_ids


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
    FILES: ClassVar[set[str]] = {
        "organizations",
        "contacts",
        "sales_orders",
        "sales_order_lines",
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
    ) -> None:
        self.directory = directory
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
        now = datetime.now(UTC)
        self.source_stale_by_system = {
            source: (now - timestamp).total_seconds() > stale_after_seconds
            for source, timestamp in observed.items()
        }
        self.source_stale = any(self.source_stale_by_system.values())
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

    def customer_overview(
        self,
        customer: str,
        scope: AccessScope,
        max_orders: int = 20,
    ) -> dict[str, Any]:
        if not customer.strip():
            raise InvalidBusinessInputError("customer is required")
        if not 1 <= max_orders <= self.MAX_ORDERS:
            raise InvalidBusinessInputError("max_orders must be between 1 and 50")

        customers = [
            row for row in self.data["organizations"] if row["roles"] == "customer"
        ]
        matches = [row for row in customers if row["canonical_id"] == customer]
        if matches:
            if not scope.allows_customer(matches[0]["canonical_id"]):
                raise ScopeDeniedError("customer is outside the authorized scope")
        else:
            needle = customer.strip().casefold()
            name_matches = [
                row for row in customers if row["name"].strip().casefold() == needle
            ]
            if not name_matches:
                raise NotFoundError("customer was not found")
            matches = [
                row
                for row in name_matches
                if scope.allows_customer(row["canonical_id"])
            ]
            if not matches:
                raise ScopeDeniedError("customer is outside the authorized scope")
        if len(matches) > 1:
            raise AmbiguousCustomerError(
                [
                    {"canonical_id": row["canonical_id"], "name": row["name"]}
                    for row in matches
                ]
            )
        organization = matches[0]
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
                "erpnext_id": self.target_ids.get(("erpnext", row["canonical_id"]), ""),
            }
            for row in self.data["sales_orders"]
            if row["customer_canonical_id"] == canonical_id
        ]
        orders.sort(
            key=lambda row: (row["order_date"], row["canonical_id"]), reverse=True
        )
        warnings = []
        if self.source_stale:
            warnings.append("source_stale")
        if self.snapshot_skew:
            warnings.append("source_snapshot_skew")
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
            "observed_at": self.observed_at,
            "source_observed_at": self.source_observed_at,
            "snapshot_skew_seconds": self.snapshot_skew_seconds,
            "sources": ["canonical-v1", "twenty", "erpnext"],
            "missing": [],
            "warnings": warnings,
        }

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
