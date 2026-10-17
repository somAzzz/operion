import unittest

from database_guard import owned_database, require_owned_database


class DatabaseIsolationTests(unittest.TestCase):
    def test_external_dsn_is_rejected_before_connection(self):
        with self.assertRaises(RuntimeError):
            require_owned_database("postgresql://localhost/important_test")

    def test_capability_is_exact_and_expires(self):
        with owned_database("owned"):
            require_owned_database("owned")
            with self.assertRaises(RuntimeError):
                require_owned_database("other")
        with self.assertRaises(RuntimeError):
            require_owned_database("owned")
