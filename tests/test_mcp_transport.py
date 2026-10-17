"""Actual client/server stdio tests, using only tracked synthetic fixtures."""

import asyncio
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


class MCPTransportTests(unittest.TestCase):
    def test_initialize_list_call_denial_and_invalid_arguments(self):
        async def check():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-c", "from operion_etl.mcp_server import main; main()"],
                cwd=str(ROOT),
                env={
                    "PYTHONPATH": str(ROOT / "src"),
                    "OPERION_OTEL_ENABLED": "0",
                    "OPERION_CANONICAL_DIR": str(ROOT / "tests/fixtures/wwi-small"),
                    "OPERION_IDENTITY_MAP": str(
                        ROOT / "tests/fixtures/wwi-small-identity.csv"
                    ),
                    "OPERION_OBSERVED_AT": "2026-10-17T00:00:00Z",
                    "OPERION_DATA_MODE": "snapshot",
                    "OPERION_COMPANY": "AI Demo GmbH",
                    "OPERION_CUSTOMER_IDS": "wwi:organization:customer:11",
                },
            )
            async with asyncio.timeout(20):
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(
                        read, write, read_timeout_seconds=10
                    ) as session:
                        initialized = await session.initialize()
                        self.assertEqual(
                            "operion-read-tools", initialized.server_info.name
                        )
                        tools = await session.list_tools()
                        self.assertEqual(15, len(tools.tools))
                        result = await session.call_tool(
                            "get_customer_overview",
                            {
                                "customer": "wwi:organization:customer:11",
                                "max_orders": 20,
                            },
                        )
                        self.assertFalse(result.is_error)
                        self.assertEqual(1, result.structured_content["order_count"])
                        denied = await session.call_tool(
                            "get_customer_overview",
                            {"customer": "wwi:organization:customer:999"},
                        )
                        self.assertTrue(denied.is_error)
                        invalid = await session.call_tool(
                            "get_customer_overview", {"max_orders": "bad"}
                        )
                        self.assertTrue(invalid.is_error)

        asyncio.run(check())
