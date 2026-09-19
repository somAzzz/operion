import csv
import json
import tempfile
import unittest
from pathlib import Path

from operion_etl.e2_data import (
    E2_CUSTOMER_NAME,
    _find_delivery_for_sales_order,
    prepare_e2_batch,
)
from operion_etl.read_tools import (
    AccessScope,
    AmbiguousCustomerError,
    CanonicalRepository,
)

BASE = Path("data/canonical/wwi-v1-small-20260919-e1")
IDENTITY = Path("reports/enterprise/e1/20260919T-e1-complete/identity_map.csv")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class E2DataTests(unittest.TestCase):
    def test_delivery_lookup_uses_submitted_sales_order_relation(self):
        class Client:
            def list(self, doctype, fields):
                self.request = (doctype, fields)
                return [
                    {"name": "DN-CANCELLED", "docstatus": 2},
                    {"name": "DN-1", "docstatus": 1},
                ]

            def get(self, doctype, name):
                return {
                    "name": name,
                    "docstatus": 1,
                    "remarks": None,
                    "items": [{"against_sales_order": "SO-1"}],
                }

        client = Client()
        result = _find_delivery_for_sales_order(client, "SO-1")
        self.assertEqual("DN-1", result["name"])
        self.assertEqual(("Delivery Note", ["name", "docstatus"]), client.request)

    def test_e2_evaluation_manifest_covers_all_fifteen_cases(self):
        manifest = json.loads(Path("evaluations/e2/cases.json").read_text())
        self.assertEqual("operion-e2-eval-v1", manifest["version"])
        self.assertEqual(3, manifest["repeat_count"])
        self.assertEqual(
            {
                "C01",
                "C02",
                "C03",
                "F01",
                "F02",
                "F03",
                "F04",
                "F05",
                "F06",
                "P01",
                "P02",
                "P03",
                "A01",
                "A02",
                "A03",
            },
            {case["id"] for case in manifest["cases"]},
        )

    def test_prepared_batch_has_real_ambiguity_and_no_order_customer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "canonical"
            identity = root / "identity.csv"
            result = prepare_e2_batch(BASE, IDENTITY, output, identity)
            self.assertEqual("prepared", result["status"])

            organizations = read_rows(output / "organizations.csv")
            ambiguous = [
                row for row in organizations if row["name"] == E2_CUSTOMER_NAME
            ]
            self.assertEqual(2, len(ambiguous))
            self.assertEqual(2, len({row["canonical_id"] for row in ambiguous}))

            orders = read_rows(output / "sales_orders.csv")
            no_order_customer = "operion:e2:organization:customer:ambiguous-b"
            self.assertFalse(
                any(row["customer_canonical_id"] == no_order_customer for row in orders)
            )

    def test_prepared_fulfillment_sources_are_isolated_and_traceable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "canonical"
            identity = root / "identity.csv"
            prepare_e2_batch(BASE, IDENTITY, output, identity)

            scenarios = read_rows(output / "fulfillment_scenarios.csv")
            self.assertEqual(6, len(scenarios))
            self.assertEqual(6, len({row["product_canonical_id"] for row in scenarios}))
            for row in scenarios:
                self.assertTrue(row["derived_from"].startswith("operion:e2:"))
                self.assertEqual(
                    "operion:e2:stock_entry:opening", row["on_hand_source"]
                )

            identity_rows = read_rows(identity)
            keys = {
                (row["canonical_id"], row["target_system"]) for row in identity_rows
            }
            customer = "operion:e2:organization:customer:ambiguous-a"
            self.assertIn((customer, "erpnext"), keys)
            self.assertIn((customer, "twenty"), keys)
            self.assertIn(("operion:e2:sales_order:F01", "erpnext"), keys)

    def test_prepared_batch_satisfies_customer_and_fulfillment_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "canonical"
            identity = root / "identity.csv"
            prepare_e2_batch(BASE, IDENTITY, output, identity)
            repository = CanonicalRepository(output, identity_map=identity)
            customer_a = "operion:e2:organization:customer:ambiguous-a"
            customer_b = "operion:e2:organization:customer:ambiguous-b"
            scope = AccessScope("AI Demo GmbH", frozenset({customer_a, customer_b}))

            overview_a = repository.customer_overview(customer_a, scope)
            overview_b = repository.customer_overview(customer_b, scope)
            self.assertEqual(7, len(overview_a["orders"]))
            self.assertEqual([], overview_b["orders"])
            with self.assertRaises(AmbiguousCustomerError):
                repository.customer_overview(E2_CUSTOMER_NAME, scope)

            expected = {
                "F01": "satisfiable",
                "F02": "satisfiable",
                "F03": "shortfall",
                "F04": "shortfall",
                "F05": "satisfiable",
                "F06": "insufficient_information",
            }
            self.assertEqual(
                expected,
                {
                    case_id: repository.fulfillment_case(case_id)["result"]
                    for case_id in expected
                },
            )


if __name__ == "__main__":
    unittest.main()
