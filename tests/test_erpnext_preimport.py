import unittest

from operion_etl.erpnext_preimport import validate_erpnext_imports


class ERPNextPreImportTests(unittest.TestCase):
    def _valid_files(self):
        return {
            "customers.csv": [
                {
                    "ID": "",
                    "Customer Name": "Customer A",
                    "Customer Group": "Commercial",
                    "Territory": "Rest Of The World",
                    "Operion Source Key": "wwi:organization:customer:1",
                }
            ],
            "suppliers.csv": [
                {
                    "ID": "",
                    "Supplier Name": "Supplier B",
                    "Supplier Group": "All Supplier Groups",
                    "Operion Source Key": "wwi:organization:supplier:2",
                }
            ],
            "items.csv": [
                {
                    "ID": "",
                    "Item Code": "wwi:product:1",
                    "Default Unit of Measure": "Unit",
                    "Maintain Stock": "1",
                    "Operion Source Key": "wwi:product:1",
                }
            ],
            "contacts.csv": [
                {
                    "ID": "",
                    "First Name": "Ada",
                    "Operion Source Key": "wwi:contact:1",
                    "Email ID (Email IDs)": "ada@example.test",
                    "Is Primary (Email IDs)": "1",
                    "Number (Contact Numbers)": "123",
                    "Is Primary Phone (Contact Numbers)": "1",
                    "Link Document Type (Links)": "Customer",
                    "Link Name (Links)": "Customer A",
                }
            ],
            "sales_orders.csv": [
                {
                    "ID": "",
                    "Customer": "Customer A",
                    "Date": "2016-05-30",
                    "Delivery Date": "2016-06-01",
                    "Company": "AI Demo GmbH",
                    "Currency": "EUR",
                    "Exchange Rate": "1",
                    "Operion Source Key": "wwi:sales_order:1",
                    "Item Code (Items)": "wwi:product:1",
                    "Delivery Date (Items)": "2016-06-01",
                    "Quantity (Items)": "2",
                    "Stock UOM (Items)": "Unit",
                    "UOM (Items)": "Unit",
                    "UOM Conversion Factor (Items)": "1",
                    "Rate (Items)": "3.00",
                    "Amount (Items)": "6.00",
                    "Operion Source Key (Items)": "wwi:sales_order_line:1",
                }
            ],
            "purchase_orders.csv": [
                {
                    "ID": "",
                    "Supplier": "Supplier B",
                    "Date": "2016-05-30",
                    "Required By": "2016-05-30",
                    "Company": "AI Demo GmbH",
                    "Currency": "EUR",
                    "Exchange Rate": "1",
                    "Operion Source Key": "wwi:purchase_order:2",
                    "Item Code (Items)": "wwi:product:1",
                    "Required By (Items)": "2016-05-30",
                    "Quantity (Items)": "5",
                    "Stock UOM (Items)": "Unit",
                    "UOM (Items)": "Unit",
                    "UOM Conversion Factor (Items)": "1",
                    "Rate (Items)": "2.00",
                    "Amount (Items)": "10.00",
                    "Operion Source Key (Items)": "wwi:purchase_order_line:1",
                }
            ],
        }

    def test_valid_files_pass(self):
        result = validate_erpnext_imports(self._valid_files())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["metrics"]["purchase_orders_items"], 1)

    def test_zero_commitment_and_broken_relation_fail(self):
        files = self._valid_files()
        files["purchase_orders.csv"][0]["Supplier"] = "Missing"
        files["purchase_orders.csv"][0]["Quantity (Items)"] = "0"
        result = validate_erpnext_imports(files)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            {error["field"] for error in result["errors"]},
            {"Supplier", "Quantity (Items)", "Amount (Items)"},
        )

    def test_sales_delivery_date_must_be_strictly_after_order_date(self):
        files = self._valid_files()
        files["sales_orders.csv"][0]["Delivery Date"] = "2016-05-30"
        files["sales_orders.csv"][0]["Delivery Date (Items)"] = "2016-05-29"
        result = validate_erpnext_imports(files)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            {error["field"] for error in result["errors"]},
            {"Delivery Date", "Delivery Date (Items)"},
        )

    def test_invalid_order_date_is_reported_without_crashing(self):
        files = self._valid_files()
        files["purchase_orders.csv"][0]["Date"] = "not-a-date"
        result = validate_erpnext_imports(files)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["field"], "Date")


if __name__ == "__main__":
    unittest.main()
