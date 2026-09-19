import asyncio
import unittest

import httpx2

from operion_etl.agent_runtime import sanitize_sglang_response


class ModelCompatibilityTests(unittest.TestCase):
    def test_sanitizes_sglang_weight_version_metadata(self):
        response = httpx2.Response(
            200,
            headers={"content-type": "application/json"},
            json={"metadata": {"weight_versions": [{"version": "default"}]}},
        )
        asyncio.run(sanitize_sglang_response(response))
        self.assertEqual(
            '[{"version":"default"}]', response.json()["metadata"]["weight_versions"]
        )

    def test_does_not_buffer_event_stream(self):
        response = httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: {}\n\n",
        )
        asyncio.run(sanitize_sglang_response(response))
        self.assertEqual(b"data: {}\n\n", response.content)


if __name__ == "__main__":
    unittest.main()
