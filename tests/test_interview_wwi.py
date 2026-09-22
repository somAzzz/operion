from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from operion_etl.interview_wwi import (
    DATASET_VERSION,
    EXPECTED_COUNTS,
    apply_interview_wwi,
    prepare_interview_wwi,
    provision_wwi_plan,
    validate_interview_wwi,
)
from operion_etl.read_tools import AccessScope, CanonicalRepository

CANONICAL = Path("data/canonical/interview-wwi-v1")
IDENTITY = Path("reports/interview-wwi-v1/identity_map.csv")


class InterviewWwiDatasetTests(unittest.TestCase):
    def test_version_rejects_seed_or_business_date_drift_before_extraction(self):
        with self.assertRaisesRegex(ValueError, "pins business_date"):
            prepare_interview_wwi(
                Path("unused"),
                Path("unused.csv"),
                business_date=date(2016, 6, 1),
            )
        with self.assertRaisesRegex(ValueError, "seed=42"):
            prepare_interview_wwi(
                Path("unused"),
                Path("unused.csv"),
                seed=43,
            )

    def test_checked_in_dataset_has_lineage_and_fixed_counts(self):
        result = validate_interview_wwi(CANONICAL)
        self.assertEqual("passed", result["status"])
        self.assertEqual(EXPECTED_COUNTS, result["counts"])
        manifest = json.loads((CANONICAL / "dataset.json").read_text())
        self.assertEqual(DATASET_VERSION, manifest["dataset_version"])
        self.assertEqual("wwi", manifest["source_system"])
        self.assertEqual("public_sample", manifest["data_class"])
        self.assertEqual(
            "wide-world-importers-v1.0", manifest["source_snapshot"]["data_version"]
        )
        self.assertEqual(663, manifest["source_profile"]["customers"])
        self.assertEqual("interview-wwi-v1.1", manifest["mapping_revision"])

    def test_identity_map_is_pending_and_unique_per_target(self):
        with IDENTITY.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        keys = [(row["target_system"], row["canonical_id"]) for row in rows]
        self.assertEqual(190, len(rows))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(row["source_system"] == "wwi" for row in rows))
        self.assertTrue(all(row["load_status"] == "pending" for row in rows))

    def test_default_provisioning_is_read_only_dry_run(self):
        plan = provision_wwi_plan(CANONICAL)
        self.assertEqual("dry_run", plan["status"])
        self.assertEqual(DATASET_VERSION, plan["dataset_version"])
        self.assertIn("14 customer-linked Person", plan["operations"][1]["objects"])

    def test_apply_fails_closed_before_any_client_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            admin_env = Path(temporary) / "admin.env"
            admin_env.write_text(
                "TWENTY_API_KEY=not-used\nERPNEXT_API_KEY=not-used\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "required safeguards"):
                apply_interview_wwi(CANONICAL, IDENTITY, admin_env)


class InterviewWwiQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = CanonicalRepository(CANONICAL, identity_map=IDENTITY)
        cls.scope = AccessScope(
            "AI Demo GmbH",
            frozenset(
                f"wwi:organization:customer:{source_id}"
                for source_id in (58, 60, 65, 88, 183, 463, 840, 935, 961, 1011)
            ),
            frozenset(
                f"wwi:organization:supplier:{source_id}"
                for source_id in (3, 6, 7, 8, 9)
            ),
        )

    def test_similar_name_search_and_zero_order_edge_cases(self):
        matches = self.repository.search_customers("Tailspin Toys", self.scope)
        self.assertEqual(5, len(matches["results"]))
        self.assertEqual(
            [],
            self.repository.customer_overview(
                "wwi:organization:customer:60", self.scope
            )["orders"],
        )
        self.assertEqual(
            10,
            len(
                self.repository.customer_overview(
                    "wwi:organization:customer:65", self.scope
                )["orders"]
            ),
        )

    def test_sales_order_retains_source_fact_and_blank_native_docstatus(self):
        detail = self.repository.get_sales_order("wwi:sales_order:66823", self.scope)
        self.assertEqual("177.60", detail["order"]["net_total_ex_tax"])
        self.assertEqual("picked", detail["order"]["source_status"])
        self.assertEqual("", detail["order"]["docstatus"])
        self.assertEqual("USD", detail["order"]["currency"])
        self.assertEqual(1, len(detail["lines"]))
        self.assertEqual("48", detail["lines"][0]["picked_quantity"])
        self.assertEqual("0", detail["lines"][0]["unpicked_quantity"])
        self.assertEqual("", detail["lines"][0]["delivered_quantity"])
        self.assertEqual(
            "unknown_not_provided_by_wwi_order_lines",
            detail["lines"][0]["delivery_evidence"],
        )
        self.assertEqual("interview-wwi-v1", detail["dataset_version"])
        self.assertEqual("2016-05-31", detail["business_date"])
        self.assertEqual(
            "current dataset and server-authorized IDs only", detail["query_scope"]
        )

    def test_purchase_order_and_zero_supplier_are_queryable(self):
        supplier = self.repository.supplier_overview(
            "wwi:organization:supplier:3", self.scope
        )
        self.assertEqual([], supplier["orders"])
        detail = self.repository.get_purchase_order(
            "wwi:purchase_order:2074", self.scope
        )
        self.assertEqual("741388.60", detail["order"]["net_total_ex_tax"])
        self.assertEqual("open", detail["order"]["source_status"])
        self.assertEqual(3, len(detail["lines"]))

    def test_purchase_detail_uses_base_units_and_independent_gold_amount(self):
        detail = self.repository.get_purchase_order(
            "wwi:purchase_order:2044", self.scope
        )
        line = next(
            row
            for row in detail["lines"]
            if row["canonical_id"] == "wwi:purchase_order_line:8240"
        )
        self.assertEqual("1592", line["ordered_outers"])
        self.assertEqual("25", line["units_per_outer"])
        self.assertEqual("39800", line["base_quantity"])
        self.assertEqual("39800", line["quantity"])
        self.assertEqual("1.900000", line["unit_price_ex_tax"])
        self.assertEqual("75620.00", line["net_amount"])


if __name__ == "__main__":
    unittest.main()
