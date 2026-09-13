import unittest

from operion_etl.preimport import normalize_domain, validate_twenty_imports


class PreImportTests(unittest.TestCase):
    def test_validator_checks_domain_identity_and_relation(self):
        companies = [{
            "Name": "A", "Id": "", "Domain Name / Link URL": "https://example.com",
            "WWI External ID": "wwi:organization:customer:1",
        }]
        people = [{
            "First Name": "P",
            "WWI External ID": "wwi:contact:1",
            "Company WWI External ID": "wwi:organization:customer:1",
        }]
        self.assertEqual(validate_twenty_imports(companies, people)["status"], "passed")
        self.assertEqual(normalize_domain("HTTP://www.Example.COM/path"), "example.com")

    def test_validator_rejects_duplicate_domain_and_broken_relation(self):
        companies = [
            {"Name": "A", "Id": "", "Domain Name / Link URL": "https://example.com", "WWI External ID": "a"},
            {"Name": "B", "Id": "", "Domain Name / Link URL": "https://example.com", "WWI External ID": "b"},
        ]
        people = [{"First Name": "P", "WWI External ID": "p", "Company WWI External ID": "missing"}]
        result = validate_twenty_imports(companies, people)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["errors"]), 3)

    def test_validator_requires_names(self):
        companies = [{
            "Name": "", "Id": "", "Domain Name / Link URL": "",
            "WWI External ID": "company",
        }]
        people = [{
            "First Name": "", "WWI External ID": "person",
            "Company WWI External ID": "company",
        }]
        result = validate_twenty_imports(companies, people)
        self.assertEqual(result["status"], "failed")
        self.assertEqual({error["field"] for error in result["errors"]}, {"Name", "First Name"})


if __name__ == "__main__":
    unittest.main()
