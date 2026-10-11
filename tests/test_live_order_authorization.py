import asyncio
import csv
import tempfile
import unittest
from pathlib import Path

from operion_etl.mcp_server import create_server
from operion_etl.read_tools import (
    AccessScope,
    InvalidBusinessInputError,
    LiveReadRepository,
    SourceUnavailableError,
)

FIXTURE = Path("tests/fixtures/wwi-small")


def first_row(name):
    with (FIXTURE / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
        return next(csv.DictReader(stream))


class ERP:
    def __init__(self, order, customer):
        self.order = order
        self.customer = customer
        self.detail = dict(order, items=[])

    def records(self, doctype, fields):
        if doctype == "Customer":
            return [self.customer]
        if doctype == "Sales Order":
            return [self.order]
        return []

    def record(self, doctype, name):
        if doctype != "Sales Order" or name != self.order["name"]:
            raise AssertionError((doctype, name))
        return self.detail


class Twenty:
    def records(self, resource):
        return []


class LiveOrderAuthorizationTests(unittest.TestCase):
    def setUp(self):
        base = first_row("sales_orders")
        self.canonical_id = base["canonical_id"]
        self.customer_id = base["customer_canonical_id"]
        self.customer = {
            "name": "CUST-A",
            "customer_name": "Customer A",
            "custom_operion_source_key": self.customer_id,
        }
        self.order = {
            "name": "SO-A",
            "custom_operion_source_key": self.canonical_id,
            "customer": "CUST-A",
            "company": "AI Demo GmbH",
            "transaction_date": "2026-10-01",
            "delivery_date": "2026-10-15",
            "status": "To Deliver",
            "docstatus": 1,
            "currency": "EUR",
            "net_total": "321.00",
        }
        self.erp = ERP(self.order, self.customer)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        identity = Path(self.temporary.name) / "identity.csv"
        identity.write_text("target_system,canonical_id,target_id,load_status\n")
        self.repository = LiveReadRepository(
            FIXTURE, identity_map=identity, twenty=Twenty(), erpnext=self.erp
        )
        self.scope = AccessScope("AI Demo GmbH", frozenset({self.customer_id}))

    def test_valid_list_and_detail(self):
        listed = self.repository.list_sales_orders(self.scope)
        self.assertEqual(1, len(listed["orders"]))
        self.assertEqual("321.00", listed["orders"][0]["net_total_ex_tax"])
        detail = self.repository.get_sales_order(self.canonical_id, self.scope)
        self.assertEqual(self.canonical_id, detail["order"]["canonical_id"])

    def test_changed_customer_is_rejected_before_list_or_detail(self):
        self.erp.customer = {
            "name": "CUST-B",
            "customer_name": "Customer B",
            "custom_operion_source_key": "wwi:organization:customer:12",
        }
        self.erp.order["customer"] = "CUST-B"
        self.erp.detail["customer"] = "CUST-B"
        for read in (
            lambda: self.repository.list_sales_orders(self.scope),
            lambda: self.repository.get_sales_order(self.canonical_id, self.scope),
        ):
            with self.assertRaises(SourceUnavailableError):
                read()

    def test_wrong_company_is_rejected(self):
        self.erp.order["company"] = "OTHER-COMPANY"
        self.erp.detail["company"] = "OTHER-COMPANY"
        with self.assertRaises(SourceUnavailableError):
            self.repository.list_sales_orders(self.scope)

    def test_detail_conflict_is_rejected(self):
        self.erp.detail["customer"] = "CUST-B"
        with self.assertRaises(SourceUnavailableError):
            self.repository.get_sales_order(self.canonical_id, self.scope)

    def test_duplicate_source_key_is_rejected(self):
        original = self.erp.records
        self.erp.records = lambda doctype, fields: (
            [self.customer, dict(self.customer, name="CUST-B")]
            if doctype == "Customer"
            else original(doctype, fields)
        )
        with self.assertRaises(SourceUnavailableError):
            self.repository.list_sales_orders(self.scope)

    def test_duplicate_order_source_key_is_rejected(self):
        original = self.erp.records
        self.erp.records = lambda doctype, fields: (
            [self.order, dict(self.order, name="SO-DUPLICATE")]
            if doctype == "Sales Order"
            else original(doctype, fields)
        )
        with self.assertRaises(SourceUnavailableError):
            self.repository.list_sales_orders(self.scope)

    def test_stale_target_id_is_rejected(self):
        self.repository.target_ids[("erpnext", self.canonical_id)] = "SO-OLD"
        with self.assertRaises(SourceUnavailableError):
            self.repository.get_sales_order(self.canonical_id, self.scope)

    def test_live_fulfillment_demo_is_unavailable(self):
        with self.assertRaises(InvalidBusinessInputError):
            self.repository.fulfillment_case("F01")
        server = create_server(self.repository, self.scope)
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertNotIn("check_fulfillment", names)
        self.assertIn("list_sales_orders", names)


class SupplierERP:
    def __init__(self, order, supplier):
        self.order = order
        self.supplier = supplier
        self.detail = dict(order, items=[])

    def records(self, doctype, fields):
        if doctype == "Supplier":
            return [self.supplier]
        if doctype == "Purchase Order":
            return [self.order]
        return []

    def record(self, doctype, name):
        if doctype != "Purchase Order" or name != self.order["name"]:
            raise AssertionError((doctype, name))
        return self.detail


class LiveSupplierAuthorizationTests(unittest.TestCase):
    def setUp(self):
        base = first_row("purchase_orders")
        self.canonical_id = base["canonical_id"]
        self.supplier_id = base["supplier_canonical_id"]
        self.supplier = {
            "name": "SUP-A",
            "supplier_name": "Supplier A",
            "custom_operion_sourcekey": self.supplier_id,
        }
        self.order = {
            "name": "PO-A",
            "custom_operion_source_key": self.canonical_id,
            "supplier": "SUP-A",
            "company": "AI Demo GmbH",
            "transaction_date": "2026-10-01",
            "schedule_date": "2026-10-15",
            "status": "To Receive",
            "docstatus": 1,
            "currency": "EUR",
            "net_total": "123.00",
        }
        self.erp = SupplierERP(self.order, self.supplier)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        identity = Path(self.temporary.name) / "identity.csv"
        identity.write_text("target_system,canonical_id,target_id,load_status\n")
        self.repository = LiveReadRepository(
            FIXTURE, identity_map=identity, twenty=Twenty(), erpnext=self.erp
        )
        self.scope = AccessScope(
            "AI Demo GmbH", frozenset(), frozenset({self.supplier_id})
        )

    def test_valid_purchase_list_and_detail(self):
        self.assertEqual(
            1, len(self.repository.list_purchase_orders(self.scope)["orders"])
        )
        detail = self.repository.get_purchase_order(self.canonical_id, self.scope)
        self.assertEqual(self.canonical_id, detail["order"]["canonical_id"])

    def test_changed_supplier_is_rejected(self):
        self.erp.supplier["name"] = "SUP-B"
        self.erp.supplier["custom_operion_sourcekey"] = "wwi:organization:supplier:999"
        self.erp.order["supplier"] = "SUP-B"
        self.erp.detail["supplier"] = "SUP-B"
        with self.assertRaises(SourceUnavailableError):
            self.repository.list_purchase_orders(self.scope)


if __name__ == "__main__":
    unittest.main()
