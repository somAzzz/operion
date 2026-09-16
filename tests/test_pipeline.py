import unittest
from decimal import Decimal

import csv
from pathlib import Path

from operion_etl.pipeline import (
    ERPNEXT_PURCHASE_ORDER_HEADERS,
    ERPNEXT_SALES_ORDER_HEADERS,
    TWENTY_COMPANY_HEADERS,
    TWENTY_PEOPLE_HEADERS,
    _erpnext_contact_rows,
    _erpnext_item_rows,
    _erpnext_purchase_order_rows,
    _erpnext_sales_order_rows,
    _number,
    _normalized_domain,
    _scenarios,
    _twenty_company_rows,
    _twenty_people_rows,
    _validate,
)


class PipelineTests(unittest.TestCase):
    def test_number_avoids_scientific_notation(self):
        self.assertEqual(_number(Decimal("70")), "70")
        self.assertEqual(_number(Decimal("2800.00")), "2800")
        self.assertEqual(_number(Decimal("2.50")), "2.5")

    def test_scenarios_are_explicitly_simulated_and_complete(self):
        canonical = {
            "sales_orders": [{"order_date": "2016-05-31"}],
            "sales_order_lines": [{
                "canonical_id": "wwi:sales_order_line:1",
                "product_canonical_id": "wwi:product:1",
                "ordered_quantity": "10",
                "uom": "Each",
            }],
        }
        rows = _scenarios(canonical)
        self.assertEqual([row["case_id"] for row in rows], ["F01", "F02", "F03", "F04", "F05", "F06"])
        self.assertEqual({row["data_class"] for row in rows}, {"simulated"})
        self.assertEqual(rows[-1]["expected_result"], "insufficient_information")
        self.assertEqual(rows[-1]["expected_inbound_date"], "")

    def test_validation_reports_broken_sales_order_reference(self):
        canonical = {
            "organizations": [], "contacts": [], "products": [], "sales_orders": [{
                "canonical_id": "wwi:sales_order:1", "source_id": "1",
                "customer_canonical_id": "wwi:organization:customer:404", "order_date": "2016-05-31",
            }],
            "sales_order_lines": [], "purchase_orders": [], "purchase_order_lines": [],
        }
        errors = _validate(canonical)
        self.assertTrue(any(error["rule"] == "reference" for error in errors))

    def test_twenty_company_export_matches_reference_template(self):
        reference = Path("data/test_data/companies-sample.csv")
        with reference.open(encoding="utf-8", newline="") as stream:
            expected_headers = next(csv.reader(stream))
        self.assertEqual(TWENTY_COMPANY_HEADERS, expected_headers[:-1] + ["WWI External ID", expected_headers[-1]])

        organization = {
            "canonical_id": "wwi:organization:customer:11",
            "address_line_1": "Unit 250",
            "address_line_2": "1432 Pullela Street",
            "city": "Devault",
            "state": "Pennsylvania",
            "country": "United States",
            "postal_code": "90185",
            "created_at": "2013-01-01",
            "updated_at": "2016-05-31T12:34:56",
            "website": "http://www.tailspintoys.com/Devault",
            "name": "Tailspin Toys (Devault, PA)",
        }
        row = _twenty_company_rows([organization])[0]
        self.assertEqual(list(row), TWENTY_COMPANY_HEADERS)
        self.assertEqual(row["Domain Name / Link URL"], "https://tailspintoys.com")
        self.assertEqual(row["Creation date"], "2013-01-01T00:00:00.000Z")
        self.assertEqual(row["Id"], "")
        self.assertEqual(row["WWI External ID"], "wwi:organization:customer:11")

    def test_twenty_company_export_blanks_all_duplicate_domains(self):
        base = {
            "address_line_1": "", "address_line_2": "", "city": "", "state": "",
            "country": "", "postal_code": "", "created_at": "", "updated_at": "",
        }
        organizations = [
            {**base, "canonical_id": "wwi:organization:customer:1", "name": "A", "website": "http://www.example.com/a"},
            {**base, "canonical_id": "wwi:organization:customer:2", "name": "B", "website": "https://example.com/b"},
        ]
        rows = _twenty_company_rows(organizations)
        self.assertEqual([row["Domain Name / Link URL"] for row in rows], ["", ""])
        self.assertEqual(_normalized_domain("http://www.Example.com/a"), "example.com")

    def test_twenty_people_use_company_external_id_relation(self):
        rows = _twenty_people_rows([{
            "canonical_id": "wwi:contact:1", "full_name": "Ada Lovelace",
            "email": "ada@example.com", "phone": "+1 555 0100",
            "company_canonical_id": "wwi:organization:customer:1",
        }])
        self.assertEqual(list(rows[0]), TWENTY_PEOPLE_HEADERS)
        self.assertEqual(rows[0]["Company WWI External ID"], "wwi:organization:customer:1")

    def test_erpnext_masters_map_uom_and_contact_relation(self):
        organizations = {
            "wwi:organization:customer:1": {
                "canonical_id": "wwi:organization:customer:1",
                "name": "Customer A", "roles": "customer",
            }
        }
        item = _erpnext_item_rows([{
            "canonical_id": "wwi:product:1", "name": "Widget",
            "uom": "Each", "unit_price_ex_tax": "12.50",
        }])[0]
        contact = _erpnext_contact_rows([{
            "canonical_id": "wwi:contact:1", "full_name": "Ada Lovelace",
            "email": "ada@example.test", "phone": "123",
            "company_canonical_id": "wwi:organization:customer:1",
        }], organizations)[0]
        self.assertEqual(item["ID"], "")
        self.assertEqual(item["Default Unit of Measure"], "Unit")
        self.assertEqual(contact["Email ID (Email IDs)"], "ada@example.test")
        self.assertEqual(contact["Is Primary (Email IDs)"], "1")
        self.assertEqual(contact["Number (Contact Numbers)"], "123")
        self.assertEqual(contact["Is Primary Phone (Contact Numbers)"], "1")
        self.assertEqual(contact["Link Document Type (Links)"], "Customer")
        self.assertEqual(contact["Link Name (Links)"], "Customer A")

    def test_erpnext_orders_combine_children_and_filter_closed_commitments(self):
        organizations = {
            "wwi:organization:customer:1": {"name": "Customer A"},
            "wwi:organization:supplier:2": {"name": "Supplier B"},
        }
        products = {"wwi:product:1": {"name": "Widget"}}
        sales = _erpnext_sales_order_rows(
            [{"canonical_id": "wwi:sales_order:1", "customer_canonical_id": "wwi:organization:customer:1",
              "order_date": "2016-05-30", "expected_delivery_date": "2016-06-01",
              "customer_po_number": "PO-1", "source_status": "open"}],
            [
                {"canonical_id": "wwi:sales_order_line:1", "sales_order_canonical_id": "wwi:sales_order:1",
                 "product_canonical_id": "wwi:product:1", "open_quantity": "2", "unit_price_ex_tax": "3", "uom": "Each"},
                {"canonical_id": "wwi:sales_order_line:2", "sales_order_canonical_id": "wwi:sales_order:1",
                 "product_canonical_id": "wwi:product:1", "open_quantity": "1", "unit_price_ex_tax": "4", "uom": "Each"},
            ], organizations, products,
        )
        purchases = _erpnext_purchase_order_rows(
            [{"canonical_id": "wwi:purchase_order:2", "supplier_canonical_id": "wwi:organization:supplier:2",
              "order_date": "2016-05-29", "expected_delivery_date": "2016-06-02",
              "supplier_reference": "REF", "source_status": "open"}],
            [
                {"canonical_id": "wwi:purchase_order_line:1", "purchase_order_canonical_id": "wwi:purchase_order:2",
                 "product_canonical_id": "wwi:product:1", "open_quantity": "5", "expected_unit_price_each": "2", "canonical_uom": "Each"},
                {"canonical_id": "wwi:purchase_order_line:2", "purchase_order_canonical_id": "wwi:purchase_order:2",
                 "product_canonical_id": "wwi:product:1", "open_quantity": "0", "expected_unit_price_each": "2", "canonical_uom": "Each"},
            ], organizations, products,
        )
        self.assertEqual(list(sales[0]), ERPNEXT_SALES_ORDER_HEADERS)
        self.assertEqual(sales[1]["Customer"], "")
        self.assertEqual(sales[1]["Operion Source Key"], "")
        self.assertEqual(sales[1]["Quantity (Items)"], "1")
        self.assertEqual(list(purchases[0]), ERPNEXT_PURCHASE_ORDER_HEADERS)
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases[0]["Quantity (Items)"], "5")


if __name__ == "__main__":
    unittest.main()
