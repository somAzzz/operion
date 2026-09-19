import asyncio
import json
import unittest
from pathlib import Path

from operion_etl.mcp_server import create_server
from operion_etl.read_tools import AccessScope, CanonicalRepository

CANONICAL = Path("data/canonical/wwi-v1-small-20260913-v4")
CUSTOMER_ID = "wwi:organization:customer:11"


class MCPServerAcceptanceTests(unittest.TestCase):
    def setUp(self):
        repository = CanonicalRepository(CANONICAL)
        scope = AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID}))
        self.server = create_server(repository, scope)

    def test_exposes_exactly_two_read_only_business_tools(self):
        tools = asyncio.run(self.server.list_tools())
        self.assertEqual(
            {"get_customer_overview", "check_fulfillment"},
            {tool.name for tool in tools},
        )
        for tool in tools:
            self.assertTrue(tool.annotations.read_only_hint)
            self.assertFalse(tool.annotations.destructive_hint)
            schema = json.dumps(tool.input_schema).casefold()
            for forbidden in ("url", "role", "scope", "token", "write", "update"):
                self.assertNotIn(forbidden, schema)

    def test_customer_scope_is_not_a_tool_argument(self):
        tools = asyncio.run(self.server.list_tools())
        overview = next(tool for tool in tools if tool.name == "get_customer_overview")
        self.assertEqual(
            {"customer", "max_orders"},
            set(overview.input_schema["properties"]),
        )

    def test_mcp_results_reuse_the_domain_implementation(self):
        overview = asyncio.run(
            self.server.call_tool(
                "get_customer_overview",
                {"customer": CUSTOMER_ID, "max_orders": 3},
            )
        )
        fulfillment = asyncio.run(
            self.server.call_tool("check_fulfillment", {"case_id": "F01"})
        )
        self.assertFalse(overview.is_error)
        self.assertFalse(fulfillment.is_error)
        self.assertEqual(
            CUSTOMER_ID,
            overview.structured_content["customer"]["canonical_id"],
        )
        self.assertEqual("satisfiable", fulfillment.structured_content["result"])


if __name__ == "__main__":
    unittest.main()
