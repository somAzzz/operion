import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from test_delivery_investigation import DATA

from operion_etl import complaint, order_records
from operion_etl.identity_readback import ERPNextReadClient, TwentyReadClient
from operion_etl.read_tools import (
    AccessScope,
    CanonicalRepository,
    NotFoundError,
    ScopeDeniedError,
)
from operion_etl.twenty import read_env
from operion_etl.wwi_delivery import WwiDeliveryReader

OWNER = complaint.CUSTOMER
ORDER = "wwi:sales_order:66823"
COMPANY = "AI Demo GmbH"
SCOPE = AccessScope(COMPANY, frozenset({OWNER}))


class RecordTests(unittest.TestCase):
    def test_wrong_order_or_wrong_customer_blocks_erp_link(self):
        key = "custom_operion_source_key"
        row = {key: ORDER, "name": "SO-1", "customer": "ONE", "company": COMPANY}
        for changed, owner in (
            ({key: "wwi:sales_order:31349"}, OWNER),
            ({}, "wwi:organization:customer:11"),
            ({"company": "Other"}, OWNER),
            ({"name": ".."}, OWNER),
        ):
            client = Mock()
            client.http.get_json.return_value = {"data": [dict(row, **changed)]}
            client.record.return_value = {"name": "ONE", key: owner}
            with self.subTest(changed=changed, owner=owner):
                result = order_records.resolve(
                    order=ORDER,
                    owner=OWNER,
                    contact=None,
                    company=COMPANY,
                    erp=client,
                    crm=None,
                )
                self.assertEqual({"status": "unavailable"}, result["sales_order"])

    def test_wrong_contact_or_company_is_never_linked(self):
        client = Mock()
        for contact, company in (
            ("wwi:contact:2", "one"),
            ("wwi:contact:1129", "other"),
        ):
            client.http.get_json.return_value = {
                "totalCount": 1,
                "data": {"people": [{"companyId": company, "wwiExternalId": contact}]},
            }
            with self.assertRaises(ValueError):
                order_records.crm_contact(client, "one", "wwi:contact:1129")

    def test_denied_or_missing_order_does_not_contact_targets(self):
        reader, crm, erp = Mock(), Mock(), Mock()
        repo = CanonicalRepository(
            DATA, delivery_reader=reader, complaint_client=crm, record_erp=erp
        )
        for source, exc in (
            (None, NotFoundError),
            (SimpleNamespace(customer_id=11, order_id=66823), ScopeDeniedError),
        ):
            reader.read.return_value = source
            with self.assertRaises(exc):
                repo.get_order_records("66823", SCOPE)
        self.assertEqual([], crm.mock_calls)
        self.assertEqual([], erp.mock_calls)


@unittest.skipUnless(
    os.getenv("OPERION_TEST_ORDER_RECORDS") == "1",
    "requires imported WWI, ERPNext and Twenty records",
)
class ImportedRecordTests(unittest.TestCase):
    def test_demo_targets_and_unrelated_note(self):
        env = read_env()
        repo = CanonicalRepository(
            DATA,
            delivery_reader=WwiDeliveryReader.from_environment(),
            complaint_client=TwentyReadClient(
                "http://localhost:3000", env["TWENTY_API_KEY_READ_ONLY"]
            ),
            record_erp=ERPNextReadClient(
                "http://localhost:8080", env["ERPNEXT_API_KEY_READ_ONLY"]
            ),
        )
        main = repo.get_order_records("66823", SCOPE)
        self.assertEqual({"sales_order", "company", "person", "note"}, set(main))
        self.assertTrue(all(v["status"] == "verified" for v in main.values()))
        other = repo.get_order_records("31349", SCOPE)
        self.assertEqual(main["company"], other["company"])
        self.assertNotIn("note", other)
        self.assertNotEqual(main["sales_order"]["id"], other["sales_order"]["id"])
