"""Server-owned facts and presentation plans. No natural-language fact extraction.

The model selects opaque references, never values, labels, units or scope. Only
allowlisted tool contracts can mint evidence. Rendering is deterministic and is
performed again at the HTTP boundary before publishing or saving an answer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .answer_presentation import (
    COVERAGE_LABELS,
    DEFAULT_COLUMNS,
    LABELS,
    TABLE_LABELS,
    context_text,
    escape_cell,
    label,
)
from .read_tools import AccessScope


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TableSelection(ClosedModel):
    table_id: str = Field(min_length=1, max_length=100)
    columns: list[str] = Field(default_factory=list, max_length=20)


class AnswerPlan(ClosedModel):
    """Choose current-turn answer_evidence references; never supply business prose.

    facts are scalar IDs. tables select server tables with optional column keys;
    an empty columns list uses the server's defaults. Tables include every row in
    the returned page. Use notice only for a non-business conversational response.
    Tool errors, missing data, scope and pagination warnings render automatically.
    """

    language: Literal["en", "zh"]
    facts: list[str] = Field(default_factory=list, max_length=40)
    tables: list[TableSelection] = Field(default_factory=list, max_length=8)
    notice: Literal["none", "needs_details", "unsupported"] = "none"


@dataclass(frozen=True)
class EvidenceContext:
    run_id: str
    scope_id: str
    tool: str
    call_index: int
    filters: str
    data_mode: str
    business_date: str
    observed_at: str
    warnings: tuple[str, ...]
    completeness: str


@dataclass(frozen=True)
class Fact:
    id: str
    entity: str
    field: str
    value: str | int
    coverage: str
    pointer: str
    context: EvidenceContext
    currency: str = ""


@dataclass(frozen=True)
class EvidenceTable:
    id: str
    kind: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str | int, ...], ...]
    pointer: str
    context: EvidenceContext


class EvidenceError(ValueError):
    def __init__(self, code: str, reference: str = ""):
        self.code, self.reference = code, reference
        super().__init__(code)


# Each adapter is tied to a server tool and a versioned domain result, not to
# model-supplied field names or an arbitrary recursive scan of JSON.
CONTRACTS = {
    "get_customer_portfolio_summary": {"customer-portfolio-v1"},
    "get_customer_order_distribution": {"customer-order-distribution-v1"},
    "get_customer_overview": {"customer-overview-v2"},
    "get_supplier_overview": {"supplier-overview-v2"},
    "get_customer_order_context": {"customer-order-context-v1"},
    "get_organization_orders": {"organization-orders-v1"},
    "search_customers": {"customer-search-v1"},
    "search_suppliers": {"supplier-search-v1"},
    "search_contacts": {"contact-search-v1"},
    "get_contact_by_name": {"contact-detail-v1"},
    "list_sales_orders": {"sales-order-list-v1"},
    "list_purchase_orders": {"purchase-order-list-v1"},
    "get_sales_order": {"sales-order-detail-v1"},
    "get_purchase_order": {"purchase-order-detail-v1"},
    "check_fulfillment": {"fulfillment-v1"},
}
RECORD_COLUMNS = (
    "canonical_id",
    "customer_id",
    "customer_name",
    "supplier_id",
    "supplier_name",
    "organization_id",
    "organization_name",
    "name",
    "full_name",
    "city",
    "country",
    "order_number",
    "order_date",
    "expected_delivery_date",
    "currency",
    "net_total_ex_tax",
    "business_status",
    "source_status",
    "docstatus",
    "source_system",
    "email",
    "phone",
    "email_state",
    "phone_state",
    "target_id",
    "twenty_id",
    "erpnext_id",
    "mapping_status",
    "product_id",
    "product_name",
    "description",
    "uom",
    "unit_price_ex_tax",
    "net_amount",
    "ordered_quantity",
    "picked_quantity",
    "delivered_quantity",
    "base_quantity",
    "quantity",
    "unpicked_quantity",
    "delivery_date",
    "case_id",
    "remaining_quantity",
    "on_hand_quantity",
    "reserved_quantity",
    "available_quantity",
    "inbound_quantity",
    "usable_inbound_quantity",
    "shortfall_quantity",
    "order_count",
)
MONEY = {"net_total_ex_tax", "unit_price_ex_tax", "net_amount"}
ERROR_CODES = {
    "ambiguous_contact": "ambiguous",
    "ambiguous_customer": "ambiguous",
    "ambiguous_supplier": "ambiguous",
    "scope_denied": "denied",
    "source_unavailable": "unavailable",
    "not_found": "not_found",
    "invalid_business_input": "invalid",
    "proposal_rejected": "unavailable",
    "proposal_unavailable": "unavailable",
}
STATUS_TEXT = {
    "ambiguous": (
        "Several records match. Choose a returned canonical ID.",
        "匹配到多个记录，请选择返回的规范 ID。",
    ),
    "denied": (
        "Access to the requested operation or record is denied.",
        "没有访问所请求操作或记录的权限。",
    ),
    "unavailable": (
        "The source is unavailable; the result is unknown, not zero.",
        "来源不可用，结果未知，不能视为零。",
    ),
    "not_found": (
        "No matching record was found in the authorized scope.",
        "授权范围内没有找到匹配记录。",
    ),
    "invalid": (
        "More precise input is required for this lookup.",
        "查询需要更准确的输入。",
    ),
}


class EvidenceRegistry:
    def __init__(
        self,
        scope: AccessScope,
        *,
        run_id: str = "",
        tenant_id: str = "",
        user_id: str = "",
    ):
        self.scope = scope
        self.run_id = run_id or uuid4().hex
        self.scope_id = hashlib.sha256(
            json.dumps(
                [
                    tenant_id,
                    user_id,
                    scope.operating_company,
                    sorted(scope.customer_ids),
                    sorted(scope.supplier_ids),
                ]
            ).encode()
        ).hexdigest()
        self._nonce = uuid4().hex[:12]
        self.facts: dict[str, Fact] = {}
        self.tables: dict[str, EvidenceTable] = {}
        self.statuses: list[tuple[EvidenceContext, str]] = []
        self.call_count = 0
        self._claims: dict[tuple[str, ...], list[tuple[str, str]]] = {}
        self._conflicts: set[str] = set()

    def _bind(self, key: tuple[str, ...], value: Any, ref: str) -> None:
        serialized = json.dumps(value, sort_keys=True)
        previous = self._claims.setdefault(key, [])
        if any(prior_value != serialized for prior_value, _ in previous):
            self._conflicts.update([ref, *(prior_ref for _, prior_ref in previous)])
        previous.append((serialized, ref))

    def _id(self, kind: str) -> str:
        return f"{self._nonce}-{kind}{len(self.facts) if kind == 'f' else len(self.tables)}"

    def _fact(
        self,
        ctx: EvidenceContext,
        entity: str,
        field: str,
        value: Any,
        pointer: str,
        coverage: str,
        currency: str = "",
    ) -> None:
        if field not in LABELS or value is None or value == "":
            return
        if field.endswith("count") or field in {"customers_with_orders"}:
            if type(value) is not int or value < 0:
                raise EvidenceError("INVALID_COUNT", pointer)
        elif not isinstance(value, (str, int)) or isinstance(value, bool):
            raise EvidenceError("INVALID_SCALAR", pointer)
        if field in MONEY:
            value = self._money(value, currency, pointer)
        fact_id = self._id("f")
        self._bind(
            (
                entity,
                field,
                coverage,
                ctx.filters
                if coverage
                in {"filtered_total", "entity_filtered_total", "returned_page"}
                else "",
            ),
            [value, currency],
            fact_id,
        )
        self.facts[fact_id] = Fact(
            fact_id, entity, field, value, coverage, pointer, ctx, currency
        )

    @staticmethod
    def _money(value: Any, currency: Any, pointer: str) -> str:
        if (
            not isinstance(currency, str)
            or len(currency) != 3
            or not currency.isascii()
            or not currency.isupper()
            or not currency.isalpha()
        ):
            raise EvidenceError("MONEY_CURRENCY_MISSING", pointer)
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise EvidenceError("INVALID_MONEY", pointer) from exc
        if not number.is_finite():
            raise EvidenceError("INVALID_MONEY", pointer)
        return format(number, "f")

    def _authorized(self, row: dict[str, Any]) -> None:
        for key, allowed in (
            ("customer_id", self.scope.customer_ids),
            ("supplier_id", self.scope.supplier_ids),
        ):
            if row.get(key) and row[key] not in allowed:
                raise EvidenceError("EVIDENCE_SCOPE_MISMATCH", key)
        if row.get("organization_id") and row["organization_id"] not in (
            self.scope.customer_ids | self.scope.supplier_ids
        ):
            raise EvidenceError("EVIDENCE_SCOPE_MISMATCH", "organization_id")
        canonical_id = row.get("canonical_id", "")
        if (
            canonical_id.startswith("wwi:organization:customer:")
            and canonical_id not in self.scope.customer_ids
        ):
            raise EvidenceError("EVIDENCE_SCOPE_MISMATCH", "canonical_id")
        if (
            canonical_id.startswith("wwi:organization:supplier:")
            and canonical_id not in self.scope.supplier_ids
        ):
            raise EvidenceError("EVIDENCE_SCOPE_MISMATCH", "canonical_id")

    def _table(
        self, ctx: EvidenceContext, kind: str, rows: list[dict[str, Any]], pointer: str
    ) -> None:
        for row in rows:
            self._authorized(row)
        rows = [dict(row) for row in rows]
        for row in rows:
            for field in ("email", "phone"):
                evidence = row.get("fields", {}).get(field, {})
                if evidence.get("status"):
                    row[field + "_state"] = evidence["status"]
        columns = tuple(
            key
            for key in RECORD_COLUMNS
            if any(key in row for row in rows)
            or key == "currency"
            and any(MONEY & row.keys() for row in rows)
        )
        if not columns:
            return
        cells = []
        for index, row in enumerate(rows):
            values = []
            for key in columns:
                value = row.get(key)
                if key in MONEY and not row.get("currency"):
                    value = None
                if key in MONEY and value not in (None, ""):
                    value = self._money(
                        value, row.get("currency"), f"{pointer}/{index}/{key}"
                    )
                if value is None or value == "":
                    value = "unknown / 未知"
                if not isinstance(value, (str, int)) or isinstance(value, bool):
                    raise EvidenceError("INVALID_SCALAR", f"{pointer}/{index}/{key}")
                if key == "order_count" and (type(value) is not int or value < 0):
                    raise EvidenceError("INVALID_COUNT", f"{pointer}/{index}/{key}")
                values.append(value)
            cells.append(tuple(values))
        table_id = self._id("t")
        for row in rows:
            identity = row.get(
                "canonical_id",
                row.get("customer_id") if kind == "customers" else row.get("case_id"),
            )
            if identity:
                for key in columns:
                    if (
                        key in row
                        and row[key] not in (None, "")
                        and not (key in MONEY and not row.get("currency"))
                    ):
                        self._bind(
                            (str(identity), key),
                            [
                                str(Decimal(str(row[key])).normalize())
                                if key in MONEY
                                else str(row[key]),
                                row.get("currency", "") if key in MONEY else "",
                            ],
                            table_id,
                        )
        self.tables[table_id] = EvidenceTable(
            table_id, kind, columns, tuple(cells), pointer, ctx
        )

    def add(
        self, tool: str, arguments: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize one actual tool result atomically; unknown schemas fail closed."""
        start_facts, start_tables, start_status = (
            set(self.facts),
            set(self.tables),
            len(self.statuses),
        )
        saved_claims = {key: list(values) for key, values in self._claims.items()}
        saved_conflicts = set(self._conflicts)
        self.call_count += 1
        data = payload.get("data", {})
        if not isinstance(data, dict):
            data = {}
        ctx = EvidenceContext(
            self.run_id,
            self.scope_id,
            tool,
            self.call_count,
            json.dumps(arguments, ensure_ascii=False, sort_keys=True),
            str(data.get("data_mode", "unknown")),
            str(data.get("business_date", "unknown")),
            str(data.get("source_observed_at", data.get("observed_at", "unknown"))),
            tuple(str(w) for w in data.get("warnings", [])),
            str(
                data.get("completeness", data.get("order_completeness", {})).get(
                    "status", "not_assessed"
                )
            ),
        )
        try:
            if payload.get("ok") is not True:
                code = payload.get("error", {}).get("code", "")
                status = ERROR_CODES.get(code, "unavailable")
                self.statuses.append((ctx, status))
                candidates = payload.get("error", {}).get("candidates", [])
                if status == "ambiguous":
                    self._table(ctx, "candidates", candidates, "/error/candidates")
            elif tool in {"check_operation_capability", "propose_followup_task"}:
                self._operation(ctx, tool, data)
            elif data.get("contract_version") not in CONTRACTS.get(tool, set()):
                raise EvidenceError("EVIDENCE_CONTRACT_UNSUPPORTED")
            elif data.get("scope_evidence", {}).get("status") == "denied":
                self.statuses.append((ctx, "denied"))
            else:
                self._domain(ctx, tool, data)
        except (EvidenceError, KeyError, TypeError, AttributeError) as exc:
            self.facts = {
                key: item for key, item in self.facts.items() if key in start_facts
            }
            self.tables = {
                key: item for key, item in self.tables.items() if key in start_tables
            }
            del self.statuses[start_status:]
            self._claims, self._conflicts = saved_claims, saved_conflicts
            self.statuses.append((ctx, "unavailable"))
            return {
                "contract": "answer-evidence-v1",
                "error": getattr(exc, "code", "EVIDENCE_SHAPE_INVALID"),
                "facts": [],
                "tables": [],
            }
        return {
            "contract": "answer-evidence-v1",
            "facts": [
                dict(
                    id=f.id,
                    entity=f.entity,
                    field=f.field,
                    value=f.value,
                    currency=f.currency,
                    coverage=f.coverage,
                    pointer=f.pointer,
                )
                for key, f in self.facts.items()
                if key not in start_facts
            ],
            "tables": [
                dict(
                    id=t.id,
                    kind=t.kind,
                    columns=t.columns,
                    returned_rows=len(t.rows),
                    pointer=t.pointer,
                )
                for key, t in self.tables.items()
                if key not in start_tables
            ],
            "statuses": [status for _, status in self.statuses[start_status:]],
        }

    def _operation(self, ctx: EvidenceContext, tool: str, data: dict[str, Any]) -> None:
        if tool == "check_operation_capability":
            operation = data.get("operation")
            status = data.get("authorization", {}).get("status")
            execution = data.get("execution", {}).get("status")
            if (
                operation not in {"read", "business_write", "propose_followup_task"}
                or status not in {"authorized", "denied"}
                or execution != "not_executed"
            ):
                raise EvidenceError("OPERATION_EVIDENCE_INVALID")
            self._fact(
                ctx,
                operation,
                "authorization",
                status,
                "/data/authorization/status",
                "capability_only",
            )
            self._fact(
                ctx,
                operation,
                "execution",
                execution,
                "/data/execution/status",
                "capability_only",
            )
        else:
            if data.get("state") != "PENDING_APPROVAL":
                raise EvidenceError("PROPOSAL_STATE_UNSUPPORTED")
            for field in ("action_id", "state"):
                self._fact(
                    ctx,
                    "proposal",
                    field,
                    data.get(field),
                    f"/data/{field}",
                    "proposal_only_not_executed",
                )

    def _domain(
        self, ctx: EvidenceContext, tool: str, data: dict[str, Any], path: str = "/data"
    ) -> None:
        if tool == "get_customer_order_context":
            self._domain(
                ctx,
                "get_customer_overview",
                data["customer_overview"],
                path + "/customer_overview",
            )
            self._domain(
                ctx, "get_sales_order", data["sales_order"], path + "/sales_order"
            )
            return
        resolution = data.get("resolution", {})
        if resolution.get("status") in STATUS_TEXT:
            self.statuses.append((ctx, resolution["status"]))
            self._table(
                ctx,
                "candidates",
                resolution.get("candidates", []),
                path + "/resolution/candidates",
            )
            return
        entity = data.get("customer", data.get("supplier", {})).get(
            "canonical_id", "authorized scope"
        )
        for key in ("customer", "supplier", "order", "contact"):
            if isinstance(data.get(key), dict):
                row = dict(data[key])
                self._authorized(row)
                if (
                    key == "customer"
                    and row.get("canonical_id") not in self.scope.customer_ids
                ):
                    raise EvidenceError("EVIDENCE_SCOPE_MISMATCH", path + "/customer")
                if (
                    key == "supplier"
                    and row.get("canonical_id") not in self.scope.supplier_ids
                ):
                    raise EvidenceError("EVIDENCE_SCOPE_MISMATCH", path + "/supplier")
                if key == "contact":
                    for field in ("email", "phone"):
                        evidence = data.get("fields", {}).get(field, {})
                        if evidence.get("state") == "present":
                            row[field] = evidence.get("value")
                        self._fact(
                            ctx,
                            row.get("canonical_id", entity),
                            field + "_state",
                            evidence.get("state"),
                            path + f"/fields/{field}/state",
                            "entity",
                        )
                self._table(ctx, key, [row], path + "/" + key)
        if tool == "get_organization_orders":
            organization = resolution.get("organization", {})
            if organization.get("canonical_id"):
                self._authorized(organization)
                entity = organization["canonical_id"]
                self._table(
                    ctx,
                    "organization",
                    [organization],
                    path + "/resolution/organization",
                )
        portfolio = tool in {
            "get_customer_portfolio_summary",
            "get_customer_order_distribution",
        }
        for field in (
            "customer_count",
            "customers_with_orders",
            "sales_order_count",
            "open_order_count",
        ):
            if portfolio and field in data:
                self._fact(
                    ctx,
                    entity,
                    field,
                    data[field],
                    path + "/" + field,
                    "portfolio_current_dataset",
                )
        kind = (
            "purchase"
            if "purchase" in tool
            or "supplier" in tool
            or data.get("order_kind") == "purchase"
            else "sales"
        )
        if "order_count" in data and data["order_count"] is not None:
            self._fact(
                ctx,
                entity,
                f"{kind}_order_count",
                data["order_count"],
                path + "/order_count",
                "entity_filtered_total",
            )
        if "orders" in data:
            orders = data["orders"]
            self._table(ctx, kind + " orders", orders, path + "/orders")
            self._fact(
                ctx,
                entity,
                "page_order_count",
                len(orders),
                path + "/orders",
                "returned_page",
            )
            completeness = data.get("completeness", {})
            total = completeness.get("total_count")
            if total is not None:
                if type(total) is not int or total < len(orders):
                    raise EvidenceError("INVALID_TOTAL_COUNT")
                self._fact(
                    ctx,
                    entity,
                    f"{kind}_order_count",
                    total,
                    path + "/completeness/total_count",
                    "filtered_total",
                )
            if kind == "sales" and all(row.get("customer_id") for row in orders):
                self._fact(
                    ctx,
                    entity,
                    "page_customer_count",
                    len({row["customer_id"] for row in orders}),
                    path + "/orders",
                    "returned_page",
                )
                if (
                    completeness.get("status") == "complete"
                    and total == len(orders)
                    and data.get("pagination", {}).get("has_more") is False
                ):
                    self._fact(
                        ctx,
                        entity,
                        "customers_with_orders",
                        len({row["customer_id"] for row in orders}),
                        path + "/orders",
                        "filtered_total",
                    )
        for key in ("customers", "contacts", "lines", "results"):
            if key in data:
                rows = [dict(row) for row in data[key]]
                if key == "lines":
                    for row in rows:
                        row.setdefault(
                            "currency", data.get("order", {}).get("currency")
                        )
                self._table(ctx, key, rows, path + "/" + key)
                if key == "results":
                    self._fact(
                        ctx,
                        entity,
                        "result_count",
                        len(rows),
                        path + "/results",
                        "returned_page",
                    )
        if tool == "check_fulfillment":
            if data.get("data_mode") != "snapshot" or data.get("result") not in {
                "satisfiable",
                "shortfall",
                "insufficient_information",
            }:
                raise EvidenceError("FULFILLMENT_EVIDENCE_INVALID")
            quantities = data.get("quantities", {})
            if quantities:
                mapping = {
                    "ordered": "ordered_quantity",
                    "delivered": "delivered_quantity",
                    "remaining": "remaining_quantity",
                    "on_hand": "on_hand_quantity",
                    "reserved_for_other_orders": "reserved_quantity",
                    "available_now": "available_quantity",
                    "unallocated_inbound": "inbound_quantity",
                    "usable_inbound_by_promise": "usable_inbound_quantity",
                    "shortfall": "shortfall_quantity",
                }
                row = {
                    "case_id": data["case_id"],
                    "uom": data.get("uom"),
                    "product_id": data.get("product_canonical_id"),
                }
                row.update(
                    {
                        field: quantities[key]
                        for key, field in mapping.items()
                        if key in quantities
                    }
                )
                self._table(ctx, "fulfillment quantities", [row], path + "/quantities")
            for key in ("case_id", "result", "promise_date", "warehouse", "uom"):
                self._fact(
                    ctx,
                    str(data.get("case_id", "scenario")),
                    key,
                    data.get(key),
                    path + "/" + key,
                    "snapshot_scenario_only",
                )

    def validate(self, plan: AnswerPlan) -> None:
        if not isinstance(plan, AnswerPlan):
            raise EvidenceError("STRUCTURED_ANSWER_REQUIRED")
        if plan.notice != "none" and self.call_count:
            raise EvidenceError("NOTICE_AFTER_BUSINESS_LOOKUP")
        if plan.notice != "none" and (plan.facts or plan.tables):
            raise EvidenceError("NOTICE_WITH_FACTS")
        if (
            not plan.facts
            and not plan.tables
            and plan.notice == "none"
            and not self.statuses
        ):
            raise EvidenceError("EMPTY_ANSWER_PLAN")
        if len(set(plan.facts)) != len(plan.facts) or len(
            {t.table_id for t in plan.tables}
        ) != len(plan.tables):
            raise EvidenceError("DUPLICATE_REFERENCE")
        for ref in plan.facts:
            fact = self.facts.get(ref)
            if fact is None:
                raise EvidenceError("FACT_REFERENCE_UNKNOWN", ref)
            self._context(fact.context)
            if ref in self._conflicts:
                raise EvidenceError("EVIDENCE_CONFLICT", ref)
        for selection in plan.tables:
            table = self.tables.get(selection.table_id)
            if table is None:
                raise EvidenceError("TABLE_REFERENCE_UNKNOWN", selection.table_id)
            self._context(table.context)
            if selection.table_id in self._conflicts:
                raise EvidenceError("EVIDENCE_CONFLICT", selection.table_id)
            if set(selection.columns) - set(table.columns) or len(
                set(selection.columns)
            ) != len(selection.columns):
                raise EvidenceError("TABLE_COLUMN_UNVERIFIED", selection.table_id)

    def _context(self, ctx: EvidenceContext) -> None:
        if ctx.run_id != self.run_id or ctx.scope_id != self.scope_id:
            raise EvidenceError("EVIDENCE_CONTEXT_MISMATCH")

    @staticmethod
    def selected_columns(table: EvidenceTable, selection: TableSelection) -> list[str]:
        chosen = set(
            selection.columns or DEFAULT_COLUMNS.get(table.kind, table.columns)
        ) & set(table.columns)
        chosen |= set(table.columns) & {
            "canonical_id",
            "customer_id",
            "supplier_id",
            "organization_id",
            "case_id",
            "product_id",
        }
        if chosen & MONEY:
            chosen.add("currency")
        if "uom" in table.columns and (
            chosen & MONEY or any(key.endswith("quantity") for key in chosen)
        ):
            chosen.add("uom")
        return [key for key in table.columns if key in chosen]

    def selection_manifest(self, plan: AnswerPlan) -> dict[str, Any]:
        """Auditable selected facts, persisted separately from model arguments."""
        self.validate(plan)
        return {
            "contract": "verified-answer-v1",
            "plan": plan.model_dump(mode="json"),
            "facts": [asdict(self.facts[ref]) for ref in plan.facts],
            "tables": [
                {
                    "id": table.id,
                    "kind": table.kind,
                    "pointer": table.pointer,
                    "context": asdict(table.context),
                    "rows": [
                        {
                            key: row[table.columns.index(key)]
                            for key in self.selected_columns(table, selection)
                        }
                        for row in table.rows
                    ],
                }
                for selection in plan.tables
                for table in [self.tables[selection.table_id]]
            ],
        }

    def render(self, plan: AnswerPlan) -> str:
        self.validate(plan)
        zh = plan.language == "zh"
        parts: list[str] = []
        contexts: dict[int, EvidenceContext] = {}
        if plan.notice != "none":
            return {
                "needs_details": (
                    "Please specify a customer, supplier, order, or scenario to look up.",
                    "请提供要查询的客户、供应商、订单或场景。",
                ),
                "unsupported": (
                    "This assistant supports authorized business lookups and follow-up proposals.",
                    "此助手支持授权范围内的业务查询和跟进提案。",
                ),
            }[plan.notice][zh]
        for ref in plan.facts:
            fact = self.facts[ref]
            contexts[fact.context.call_index] = fact.context
            entity = (
                ""
                if fact.entity == "authorized scope"
                else escape_cell(fact.entity) + " — "
            )
            coverage = COVERAGE_LABELS[fact.coverage][zh]
            parts.append(
                f"{entity}{label(fact.field, plan.language)} ({coverage}): **{escape_cell(fact.value)}{(' ' + escape_cell(fact.currency)) if fact.currency else ''}**. [E{fact.context.call_index}]"
            )
        for selection in plan.tables:
            table = self.tables[selection.table_id]
            contexts[table.context.call_index] = table.context
            columns = self.selected_columns(table, selection)
            parts.append(
                f"{TABLE_LABELS[table.kind][zh]} [E{table.context.call_index}]\n\n| "
                + " | ".join(label(key, plan.language) for key in columns)
                + " |\n| "
                + " | ".join("---" for _ in columns)
                + " |\n"
                + "\n".join(
                    "| "
                    + " | ".join(
                        escape_cell(row[table.columns.index(key)]) for key in columns
                    )
                    + " |"
                    for row in table.rows
                )
            )
        for ctx, status in self.statuses:
            self._context(ctx)
            contexts[ctx.call_index] = ctx
            parts.append(STATUS_TEXT[status][zh])
        for ctx in contexts.values():
            parts.append(context_text(ctx, zh))
        return "\n\n".join(parts)
