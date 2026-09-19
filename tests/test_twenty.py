import unittest

from operion_etl.twenty import TwentyClient


class TwentyClientTests(unittest.TestCase):
    def test_records_follow_cursor_pagination(self):
        client = TwentyClient("http://twenty.test", "test-key")
        calls = []

        def request(path, payload=None):
            calls.append((path, payload))
            if "starting_after" not in path:
                return {
                    "data": {"companies": [{"id": "company-1"}]},
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                }
            return {
                "data": {"companies": [{"id": "company-2"}]},
                "pageInfo": {"hasNextPage": False},
            }

        client._request = request
        self.assertEqual([{"id": "company-1"}, {"id": "company-2"}], client.companies())
        self.assertEqual(2, len(calls))
        self.assertIn("starting_after=cursor-1", calls[1][0])


if __name__ == "__main__":
    unittest.main()
