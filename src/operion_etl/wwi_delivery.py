import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pymssql
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .delivery_evidence import Invoice, build_investigation


class StockReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: int
    purchase_order_id: int
    supplier_id: int
    supplier: str
    stock_item_id: int
    quantity: Decimal = Field(gt=0)
    received_at: datetime


class StockIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: int
    invoice_id: int
    stock_item_id: int
    quantity: Decimal = Field(lt=0)
    issued_at: datetime
    prior_receipts: list[StockReceipt]


class DeliveryLine(BaseModel):
    canonical_id: str
    stock_item_id: int
    ordered_quantity: int
    picked_quantity: int | None
    uom: str


class DeliveryOrder(BaseModel):
    order_id: int
    customer_id: int
    contact_person_id: int | None = Field(default=None, gt=0)
    order_date: str
    expected_date: str
    queried_at: AwareDatetime
    invoices: list[Invoice]
    lines: list[DeliveryLine]
    issues: list[StockIssue]

    def investigation(
        self, subject: str, customers: frozenset[str], suppliers: frozenset[str]
    ) -> dict:
        owner = f"wwi:organization:customer:{self.customer_id}"
        if subject != f"wwi:sales_order:{self.order_id}" or owner not in customers:
            raise ValueError("WWI order scope mismatch")
        invoices = {i.invoice_id for i in self.invoices if not i.credit_note}
        items = {line.stock_item_id for line in self.lines}
        for issue in self.issues:
            if issue.invoice_id not in invoices or issue.stock_item_id not in items:
                raise ValueError("stock issue outside order scope")
            for receipt in issue.prior_receipts:
                if (
                    receipt.stock_item_id != issue.stock_item_id
                    or receipt.received_at > issue.issued_at
                    or f"wwi:organization:supplier:{receipt.supplier_id}"
                    not in suppliers
                ):
                    raise ValueError("invalid prior receipt context")
        queried_at = self.queried_at.isoformat()
        return build_investigation(
            subject,
            owner,
            self.expected_date,
            [line.model_dump() for line in self.lines],
            self.invoices,
            {
                "issues": [i.model_dump(mode="json") for i in self.issues],
                "stock_allocation": "not_evidenced",
                "receipt_scope": "two_most_recent_authorized_receipts_per_issue",
                "data_mode": "live",
                "source_system": "wwi",
                "data_class": "public_sample",
                "queried_at": queried_at,
                "source_observed_at": queried_at,
                "business_date": self.order_date,
                "completeness": {
                    "status": "complete",
                    "scope": "all_linked_invoices_for_authorized_order",
                },
            },
        )


@dataclass(frozen=True)
class WwiDeliveryReader:
    password_file: Path
    host: str = "127.0.0.1"
    port: int = 1433

    @classmethod
    def from_environment(cls):
        return cls(
            Path(
                os.environ.get(
                    "OPERION_WWI_PASSWORD_FILE",
                    "var/demo/wwi-delivery-password",
                )
            ),
            os.environ.get("OPERION_WWI_HOST", "127.0.0.1"),
            int(os.environ.get("OPERION_WWI_PORT", "1433")),
        )

    def read(
        self, order_id: int, customers: list[int], suppliers: list[int]
    ) -> DeliveryOrder | None:
        password = self.password_file.read_text().strip()
        if not password:
            raise OSError("missing reader credential")
        try:
            with (
                pymssql.connect(
                    server=self.host,
                    port=str(self.port),
                    database="WideWorldImporters",
                    user="operion_delivery_reader",
                    password=password,
                    login_timeout=3,
                    timeout=5,
                    autocommit=True,
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "EXEC dbo.operion_read_delivery %s, %s, %s",
                    (order_id, json.dumps(customers), json.dumps(suppliers)),
                )
                payload = "".join(row[0] for row in cursor)
        except pymssql.Error as error:
            raise OSError("WWI delivery query failed") from error
        rows = json.loads(payload)
        if rows == []:
            return None
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("unexpected WWI order result")
        return DeliveryOrder.model_validate(rows[0])
