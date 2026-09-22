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
from operion_etl.read_tools import (
    AccessScope,
    CanonicalRepository,
    InvalidBusinessInputError,
    LiveReadRepository,
    NotFoundError,
    ScopeDeniedError,
    SourceUnavailableError,
)

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


class FakeLiveERPNext:
    def __init__(self, *, valid_link: bool = True):
        self.valid_link = valid_link

    def records(self, doctype, fields):
        if doctype == "Supplier":
            return [
                {
                    "name": "SUP-7",
                    "supplier_name": "Litware, Inc.",
                    "custom_operion_sourcekey": "wwi:organization:supplier:7",
                }
            ]
        if doctype == "Contact":
            return [
                {
                    "name": "CONT-33",
                    "first_name": "Elias",
                    "last_name": "Myllari",
                    "custom_operion_source_key": "wwi:contact:33",
                }
            ]
        if doctype == "Customer":
            return [
                {
                    "name": "CUST-65",
                    "customer_name": "Tailspin Toys",
                    "custom_operion_source_key": "wwi:organization:customer:65",
                }
            ]
        return []

    def record(self, doctype, name):
        if doctype != "Contact" or name != "CONT-33":
            raise AssertionError((doctype, name))
        return {
            "custom_operion_source_key": "wwi:contact:33",
            "links": [
                {
                    "link_doctype": "Supplier",
                    "link_name": "SUP-7" if self.valid_link else "SUP-OTHER",
                }
            ],
            "email_ids": [
                {"email_id": "other@example.invalid", "is_primary": 0},
                {"email_id": "live-elias@litwareinc.com", "is_primary": 1},
            ],
            "phone_nos": [{"phone": "+1 209 555 9999", "is_primary_phone": 1}],
        }


class FakeLiveTwenty:
    def __init__(self, *, valid_link: bool = True):
        self.valid_link = valid_link

    def records(self, resource):
        if resource == "companies":
            return [
                {
                    "id": "TW-65",
                    "name": "Tailspin Toys",
                    "wwiExternalId": "wwi:organization:customer:65",
                }
            ]
        if resource == "people":
            return [
                {
                    "id": "PERSON-1129",
                    "wwiExternalId": "wwi:contact:1129",
                    "companyId": "TW-65" if self.valid_link else "TW-OTHER",
                    "name": {"firstName": "Hanuman", "lastName": "Dubey"},
                    "emails": {"primaryEmail": "live-hanuman@tailspintoys.com"},
                    "phones": {"primaryPhoneNumber": "+1 210 555 9999"},
                }
            ]
        return []


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

    def test_portfolio_summary_includes_total_sales_orders_in_scope(self):
        summary = self.repository.customer_portfolio_summary(self.scope)
        self.assertEqual(10, summary["customer_count"])
        self.assertEqual(8, summary["customers_with_orders"])
        self.assertEqual(30, summary["sales_order_count"])
        self.assertEqual(15, summary["open_order_count"])

    def test_distribution_is_complete_and_includes_zero_order_customers(self):
        result = self.repository.customer_order_distribution(self.scope)
        counts = {row["customer_id"]: row for row in result["customers"]}
        self.assertEqual(30, result["sales_order_count"])
        self.assertEqual(10, result["customer_count"])
        self.assertEqual("complete", result["completeness"]["status"])
        self.assertEqual(
            "none_in_current_scope",
            counts["wwi:organization:customer:60"]["order_presence"],
        )
        self.assertEqual(0, counts["wwi:organization:customer:88"]["order_count"])
        self.assertEqual("undetermined", result["completeness"]["full_source_history"])

    def test_organization_order_resolution_and_coverage_are_server_side(self):
        litware = self.repository.get_organization_orders("Litware", self.scope)
        self.assertEqual("resolved", litware["resolution"]["status"])
        self.assertEqual(
            "supplier", litware["resolution"]["organization"]["relationship"]
        )
        self.assertEqual("purchase", litware["order_kind"])
        self.assertEqual(15, litware["order_count"])
        self.assertEqual("complete", litware["completeness"]["status"])
        self.assertEqual(15, len({row["canonical_id"] for row in litware["orders"]}))
        partial = self.repository.get_organization_orders(
            "Litware", self.scope, limit=3
        )
        self.assertEqual("partial", partial["completeness"]["status"])
        self.assertEqual(3, len(partial["orders"]))
        self.assertEqual(15, partial["order_count"])
        ambiguous = self.repository.get_organization_orders("Tailspin Toys", self.scope)
        self.assertEqual("ambiguous", ambiguous["resolution"]["status"])
        self.assertFalse(ambiguous["orders"])
        denied = self.repository.get_organization_orders(
            "wwi:organization:supplier:7",
            AccessScope("AI Demo GmbH", frozenset()),
        )
        self.assertEqual("denied", denied["resolution"]["status"])
        self.assertEqual([], denied["resolution"]["candidates"])

    def test_numeric_customer_ids_resolve_in_overview_and_filtered_order_list(self):
        overview = self.repository.customer_overview("60", self.scope)
        self.assertEqual(
            "wwi:organization:customer:60", overview["customer"]["canonical_id"]
        )
        self.assertEqual("none_in_current_scope", overview["order_presence"])
        self.assertEqual("complete", overview["order_completeness"]["status"])
        self.assertEqual(
            "undetermined", overview["order_completeness"]["full_source_history"]
        )
        listed = self.repository.list_sales_orders(self.scope, customer_id="60")
        self.assertEqual(0, listed["completeness"]["total_count"])
        self.assertEqual("complete", listed["completeness"]["status"])
        with self.assertRaises(ScopeDeniedError):
            self.repository.customer_overview(
                "60", AccessScope("AI Demo GmbH", frozenset())
            )

    def test_source_status_and_delivery_evidence_are_structured(self):
        detail = self.repository.get_sales_order("66823", self.scope)
        self.assertEqual(
            "unknown", detail["order"]["status_interpretation"]["confirmation_status"]
        )
        self.assertEqual("picked", detail["order"]["source_status"])
        self.assertEqual("unknown", detail["lines"][0]["delivery_state"]["status"])
        self.assertEqual(
            "present",
            self.repository.supplier_overview("7", self.scope)["contacts"][0]["fields"][
                "email"
            ]["status"],
        )
        self.assertEqual(
            0,
            self.repository.list_sales_orders(self.scope, status="draft")[
                "completeness"
            ]["total_count"],
        )

    def test_numeric_wwi_order_ids_resolve_without_extra_lookups(self):
        sales = self.repository.get_sales_order("66823", self.scope)
        purchase = self.repository.get_purchase_order("2044", self.scope)
        self.assertEqual("wwi:sales_order:66823", sales["order"]["canonical_id"])
        self.assertEqual("wwi:purchase_order:2044", purchase["order"]["canonical_id"])
        self.assertEqual("723322.40", purchase["order"]["net_total_ex_tax"])
        customer_only = AccessScope(
            "AI Demo GmbH", frozenset({"wwi:organization:customer:65"})
        )
        with self.assertRaises(ScopeDeniedError):
            self.repository.get_purchase_order("2044", customer_only)

    def test_contact_detail_is_resolved_and_attributed_server_side(self):
        detail = self.repository.get_contact_by_name("Elias Myllari", self.scope)
        self.assertEqual("wwi:contact:33", detail["contact"]["canonical_id"])
        self.assertEqual("pending", detail["contact"]["mapping_status"])
        self.assertEqual("present", detail["fields"]["email"]["state"])
        self.assertEqual("eliasm@litwareinc.com", detail["fields"]["email"]["value"])
        self.assertEqual("(209) 555-0101", detail["fields"]["phone"]["value"])
        self.assertEqual("wwi", detail["fields"]["phone"]["source_system"])
        self.assertEqual("canonical_snapshot", detail["fields"]["phone"]["data_origin"])
        self.assertEqual(
            {"status": "not_verified", "reason": "snapshot_only"},
            detail["cross_system_verification"],
        )
        self.assertEqual(["wwi"], detail["source_system"])
        self.assertNotIn("queried_systems", detail)
        customer_only = AccessScope(
            "AI Demo GmbH", frozenset({"wwi:organization:customer:65"})
        )
        with self.assertRaises(NotFoundError):
            self.repository.get_contact_by_name("Elias Myllari", customer_only)

    def test_customer_order_context_resolves_name_and_rejects_mismatch(self):
        result = self.repository.get_customer_order_context(
            "Tailspin Toys", "66823", self.scope
        )
        self.assertEqual(
            "verified_by_sales_order_customer_id", result["resolution"]["status"]
        )
        self.assertEqual(
            "wwi:organization:customer:65", result["resolution"]["customer_id"]
        )
        self.assertEqual(10, len(result["customer_overview"]["orders"]))
        self.assertEqual("48", result["sales_order"]["lines"][0]["picked_quantity"])
        with self.assertRaises(InvalidBusinessInputError):
            self.repository.get_customer_order_context(
                "Wingtip Toys", "66823", self.scope
            )

    def test_contact_search_finds_elias_without_disclosing_other_scopes(self):
        result = self.repository.search_contacts("Elias Myllari", self.scope)
        self.assertEqual(1, len(result["results"]))
        contact = result["results"][0]
        self.assertEqual("wwi:contact:33", contact["canonical_id"])
        self.assertEqual("wwi:organization:supplier:7", contact["organization_id"])
        self.assertEqual("supplier", contact["organization_role"])
        self.assertEqual("pending", contact["mapping_status"])
        self.assertNotIn("email", contact)
        self.assertNotIn("phone", contact)
        self.assertEqual(["wwi"], result["source_system"])
        self.assertEqual("canonical_snapshot", result["data_origin"])
        self.assertEqual(
            "2026-09-12T10:03:59.810871+00:00",
            result["source_observed_at"]["wwi"],
        )
        customer_only = AccessScope(
            "AI Demo GmbH", frozenset({"wwi:organization:customer:65"})
        )
        self.assertEqual(
            [],
            self.repository.search_contacts("Elias Myllari", customer_only)["results"],
        )

    def test_scoped_supplier_and_customer_contacts_include_sample_details(self):
        supplier = self.repository.supplier_overview(
            "wwi:organization:supplier:7", self.scope
        )
        elias = next(
            row
            for row in supplier["contacts"]
            if row["canonical_id"] == "wwi:contact:33"
        )
        self.assertEqual("eliasm@litwareinc.com", elias["email"])
        self.assertEqual("(209) 555-0101", elias["phone"])
        self.assertEqual("pending", elias["erpnext_mapping_status"])
        self.assertEqual("pending", supplier["supplier"]["erpnext_mapping_status"])
        customer = self.repository.customer_overview(
            "wwi:organization:customer:65", self.scope
        )
        self.assertTrue(
            all(row["email"] and row["phone"] for row in customer["contacts"])
        )

    def test_live_new_queries_use_live_authorized_rows(self):
        repository = LiveReadRepository(
            CANONICAL,
            identity_map=IDENTITY,
            twenty=FakeLiveTwenty(),
            erpnext=FakeLiveERPNext(),
        )
        supplier = repository.get_organization_orders("Litware", self.scope)
        self.assertEqual("resolved", supplier["resolution"]["status"])
        self.assertEqual("live", supplier["source_read"]["status"])
        self.assertEqual(0, supplier["order_count"])
        distribution = repository.customer_order_distribution(self.scope)
        self.assertEqual(1, distribution["customer_count"])
        self.assertEqual("partial", distribution["completeness"]["status"])
        self.assertEqual("live", distribution["source_read"]["status"])

    def test_live_contact_search_keeps_twenty_and_erpnext_people_distinct(self):
        repository = LiveReadRepository(
            CANONICAL,
            identity_map=IDENTITY,
            twenty=FakeLiveTwenty(),
            erpnext=FakeLiveERPNext(),
        )
        elias = repository.search_contacts("Elias Myllari", self.scope)
        hanuman = repository.search_contacts("Hanuman Dubey", self.scope)
        self.assertEqual("erpnext", elias["results"][0]["source_system"])
        self.assertEqual("verified_live", elias["results"][0]["mapping_status"])
        self.assertEqual("supplier", elias["results"][0]["organization_role"])
        self.assertEqual("twenty", hanuman["results"][0]["source_system"])
        self.assertEqual("verified_live", hanuman["results"][0]["mapping_status"])
        self.assertEqual("customer", hanuman["results"][0]["organization_role"])
        self.assertEqual("live_adapters", hanuman["data_origin"])
        detail = repository.get_contact_by_name("Elias Myllari", self.scope)
        self.assertEqual(
            "live-elias@litwareinc.com", detail["fields"]["email"]["value"]
        )
        self.assertEqual("erpnext", detail["fields"]["email"]["source_system"])
        self.assertEqual("verified_live", detail["contact"]["mapping_status"])

    def test_live_supplier_contact_uses_verified_erpnext_values(self):
        repository = LiveReadRepository(
            CANONICAL,
            identity_map=IDENTITY,
            twenty=FakeLiveTwenty(),
            erpnext=FakeLiveERPNext(),
        )
        result = repository.supplier_overview("wwi:organization:supplier:7", self.scope)
        self.assertEqual("live-elias@litwareinc.com", result["contacts"][0]["email"])
        self.assertEqual("+1 209 555 9999", result["contacts"][0]["phone"])

    def test_live_customer_contact_uses_verified_twenty_values(self):
        repository = LiveReadRepository(
            CANONICAL,
            identity_map=IDENTITY,
            twenty=FakeLiveTwenty(),
            erpnext=FakeLiveERPNext(),
        )
        result = repository.customer_overview(
            "wwi:organization:customer:65", self.scope
        )
        self.assertEqual(1, len(result["contacts"]))
        self.assertEqual(
            "live-hanuman@tailspintoys.com", result["contacts"][0]["email"]
        )
        self.assertEqual("+1 210 555 9999", result["contacts"][0]["phone"])

    def test_live_contact_relation_mismatch_fails_closed(self):
        supplier_repository = LiveReadRepository(
            CANONICAL,
            identity_map=IDENTITY,
            twenty=FakeLiveTwenty(),
            erpnext=FakeLiveERPNext(valid_link=False),
        )
        with self.assertRaises(SourceUnavailableError):
            supplier_repository.supplier_overview(
                "wwi:organization:supplier:7", self.scope
            )
        customer_repository = LiveReadRepository(
            CANONICAL,
            identity_map=IDENTITY,
            twenty=FakeLiveTwenty(valid_link=False),
            erpnext=FakeLiveERPNext(),
        )
        with self.assertRaises(SourceUnavailableError):
            customer_repository.customer_overview(
                "wwi:organization:customer:65", self.scope
            )

    def test_sales_order_breakdown_reconciles_with_returned_page(self):
        result = self.repository.list_sales_orders(self.scope, limit=50)
        counts = {
            row["customer_id"]: row["order_count"]
            for row in result["customer_order_counts"]
        }
        self.assertEqual("returned_page", result["customer_order_counts_scope"])
        self.assertEqual(30, result["pagination"]["page_count"])
        self.assertFalse(result["pagination"]["has_more"])
        self.assertEqual(30, sum(counts.values()))
        self.assertEqual(10, counts["wwi:organization:customer:65"])
        self.assertNotIn("wwi:organization:customer:60", counts)
        self.assertNotIn("wwi:organization:customer:88", counts)

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
