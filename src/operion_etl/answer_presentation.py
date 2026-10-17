"""Fixed bilingual labels and safe formatting for server-owned business evidence."""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .answer_evidence import EvidenceContext

LABELS = {
    "customer_count": ("Customers", "客户数"),
    "customers_with_orders": ("Customers with sales orders", "有销售订单的客户数"),
    "sales_order_count": ("Sales orders", "销售订单数"),
    "purchase_order_count": ("Purchase orders", "采购订单数"),
    "open_order_count": (
        "Open sales orders (source open or natively confirmed)",
        "未结销售订单数（来源 open 或系统已确认）",
    ),
    "page_order_count": ("Orders returned on this page", "本页返回的订单数"),
    "page_customer_count": (
        "Customers represented on this page",
        "本页订单涉及的客户数",
    ),
    "result_count": ("Matching records", "匹配记录数"),
    "canonical_id": ("Canonical ID", "规范 ID"),
    "customer_id": ("Customer ID", "客户 ID"),
    "supplier_id": ("Supplier ID", "供应商 ID"),
    "organization_id": ("Organization ID", "组织 ID"),
    "name": ("Name", "名称"),
    "full_name": ("Full name", "姓名"),
    "customer_name": ("Customer", "客户"),
    "supplier_name": ("Supplier", "供应商"),
    "organization_name": ("Organization", "组织"),
    "city": ("City", "城市"),
    "country": ("Country", "国家"),
    "order_number": ("Order number", "订单号"),
    "order_date": ("Order date", "订单日期"),
    "expected_delivery_date": ("Expected delivery date", "预计交付日期"),
    "net_total_ex_tax": ("Net total excluding tax", "不含税净额"),
    "unit_price_ex_tax": ("Unit price excluding tax", "不含税单价"),
    "net_amount": ("Line net amount", "行净额"),
    "currency": ("Currency", "币种"),
    "business_status": ("Business status", "业务状态"),
    "source_status": ("Source status", "来源状态"),
    "docstatus": ("Native document status", "系统单据状态"),
    "source_system": ("Source system", "来源系统"),
    "order_count": ("Sales orders for this customer", "该客户的销售订单数"),
    "email": ("Email", "电子邮件"),
    "phone": ("Phone", "电话"),
    "email_state": ("Email evidence state", "电子邮件证据状态"),
    "phone_state": ("Phone evidence state", "电话证据状态"),
    "target_id": ("Target record ID", "目标记录 ID"),
    "twenty_id": ("Twenty ID", "Twenty ID"),
    "erpnext_id": ("ERPNext ID", "ERPNext ID"),
    "mapping_status": ("Mapping status", "映射状态"),
    "product_id": ("Product ID", "产品 ID"),
    "product_name": ("Product", "产品"),
    "description": ("Description", "描述"),
    "uom": ("Unit", "单位"),
    "ordered_quantity": ("Ordered quantity", "订购数量"),
    "picked_quantity": ("Picked quantity", "拣货数量"),
    "delivered_quantity": ("Delivered quantity", "已交付数量"),
    "base_quantity": ("Base quantity", "基本数量"),
    "quantity": ("Quantity", "数量"),
    "unpicked_quantity": ("Unpicked quantity", "未拣货数量"),
    "delivery_date": ("Delivery date", "交付日期"),
    "remaining_quantity": ("Remaining quantity", "剩余数量"),
    "on_hand_quantity": ("On-hand quantity", "现有库存数量"),
    "reserved_quantity": ("Reserved for other orders", "为其他订单预留数量"),
    "available_quantity": ("Available now", "当前可用数量"),
    "inbound_quantity": ("Unallocated inbound quantity", "未分配入库数量"),
    "usable_inbound_quantity": (
        "Inbound usable by promise date",
        "承诺日期前可用入库数量",
    ),
    "shortfall_quantity": ("Shortfall quantity", "缺口数量"),
    "result": ("Snapshot fulfillment result", "快照履约结果"),
    "case_id": ("Scenario ID", "场景 ID"),
    "promise_date": ("Promise date", "承诺日期"),
    "warehouse": ("Warehouse", "仓库"),
    "authorization": ("Operation authorization", "操作授权"),
    "execution": ("Operation execution", "操作执行"),
    "resolution": ("Resolution", "解析结果"),
    "action_id": ("Proposal ID", "提案 ID"),
    "state": ("Proposal state", "提案状态"),
}


def escape_cell(value: Any) -> str:
    # Source strings are data, including malicious Markdown and HTML in names.
    value = str(value).replace("\n", " ").replace("\r", " ")
    for symbol in ("\\", "|", "`", "*", "_", "[", "]", "(", ")", "#", "!"):
        value = value.replace(symbol, "\\" + symbol)
    return html.escape(value, quote=False)


def label(field: str, language: str) -> str:
    return LABELS[field][language == "zh"]


COVERAGE_LABELS = {
    "portfolio_current_dataset": ("current authorized dataset", "当前授权数据集"),
    "filtered_total": ("filtered total", "筛选总数"),
    "entity_filtered_total": ("total for this organization", "该组织的总数"),
    "returned_page": ("returned page", "本页返回结果"),
    "entity": ("record evidence", "记录证据"),
    "capability_only": (
        "capability only; no operation executed",
        "仅能力检查，未执行操作",
    ),
    "proposal_only_not_executed": ("proposal only; not executed", "仅提案，尚未执行"),
    "snapshot_scenario_only": ("snapshot scenario only", "仅快照场景"),
}
TABLE_LABELS = {
    "fulfillment quantities": ("Snapshot fulfillment quantities", "快照履约数量"),
    "sales orders": ("Sales orders", "销售订单"),
    "purchase orders": ("Purchase orders", "采购订单"),
    "customers": ("Order counts by customer", "各客户订单数"),
    "customer": ("Customer", "客户"),
    "supplier": ("Supplier", "供应商"),
    "organization": ("Organization", "组织"),
    "order": ("Order", "订单"),
    "contact": ("Contact", "联系人"),
    "contacts": ("Contacts", "联系人"),
    "lines": ("Order lines", "订单行"),
    "results": ("Search results", "查询结果"),
    "candidates": ("Matching candidates", "候选记录"),
}
DEFAULT_COLUMNS = {
    "sales orders": (
        "canonical_id",
        "customer_name",
        "order_number",
        "order_date",
        "currency",
        "net_total_ex_tax",
        "business_status",
        "source_status",
    ),
    "purchase orders": (
        "canonical_id",
        "supplier_name",
        "order_number",
        "order_date",
        "currency",
        "net_total_ex_tax",
        "business_status",
        "source_status",
    ),
}


def context_text(ctx: EvidenceContext, zh: bool) -> str:
    mode = {
        "snapshot": ("Snapshot", "数据快照"),
        "live": ("Upstream read", "上游读取"),
        "unknown": ("Source mode unknown", "来源模式未知"),
    }.get(ctx.data_mode, ("Source mode unknown", "来源模式未知"))[zh]
    completeness = {
        "complete": ("complete", "完整"),
        "partial": ("partial; more records may exist", "部分结果，可能仍有更多记录"),
        "not_assessed": ("not assessed", "未评估"),
    }.get(ctx.completeness, ("not assessed", "未评估"))[zh]
    filter_labels = {
        "limit": ("Page size", "每页条数"),
        "max_orders": ("Maximum returned orders", "最多返回订单数"),
        "customer": ("Customer", "客户"),
        "customer_id": ("Customer", "客户"),
        "supplier": ("Supplier", "供应商"),
        "supplier_id": ("Supplier", "供应商"),
        "date_from": ("From", "开始日期"),
        "date_to": ("To", "结束日期"),
        "status": ("Status", "状态"),
        "query": ("Search", "查询"),
        "name": ("Name", "姓名"),
        "order_id": ("Order", "订单"),
        "case_id": ("Scenario", "场景"),
        "operation": ("Operation", "操作"),
        "relationship": ("Relationship", "组织关系"),
        "customer_query": ("Customer search", "客户查询"),
    }
    filters = []
    for key, value in json.loads(ctx.filters).items():
        if value is None:
            continue
        if key == "cursor":
            filters.append("Following page" if not zh else "后续分页")
        elif key in filter_labels:
            if key == "customer" and value == "*":
                value = "全部授权客户" if zh else "All authorized customers"
            filters.append(f"{filter_labels[key][zh]}: {escape_cell(value)}")
        else:
            filters.append(
                "其他条件见来源证据"
                if zh
                else "Additional conditions in source evidence"
            )
    filters = "; ".join(filters) or ("无附加筛选" if zh else "No additional filters")
    warning_labels = {
        "source_stale": ("Source observation may be stale", "来源观测可能已过期"),
        "source_snapshot_skew": (
            "Source observation times differ",
            "来源观测时间不一致",
        ),
        "frozen_fulfillment_snapshot": (
            "Frozen fulfillment scenario",
            "固定履约快照场景",
        ),
    }
    warnings = "; ".join(
        warning_labels.get(w, ("Additional source limitation", "来源存在其他限制"))[zh]
        for w in ctx.warnings
        if w != "snapshot_not_live"
    )
    if zh:
        return (
            f"E{ctx.call_index} · {mode} · 业务日期：{escape_cell(ctx.business_date)}。范围：当前数据集及服务器授权记录；结果完整性：{completeness}。查询条件：{filters}。不代表全部历史或实时状态。"
            + (f" 来源提示：{warnings}。" if warnings else "")
        )
    return (
        f"E{ctx.call_index} · {mode} · Business date: {escape_cell(ctx.business_date)}. Scope: current dataset and server-authorized records. Result completeness: {completeness}. Filters: {filters}. This does not establish full source history or real-time state."
        + (f" Source warnings: {warnings}." if warnings else "")
    )
