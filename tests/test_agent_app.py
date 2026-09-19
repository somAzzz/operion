import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai import CancellationToken
from pydantic_ai.messages import ModelMessage, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from operion_etl.agent_app import AgentApplication, create_app
from operion_etl.agent_runtime import AgentSettings, create_operion_agent
from operion_etl.read_tools import AccessScope, CanonicalRepository
from operion_etl.session_store import ConversationStore

CANONICAL = Path("data/canonical/wwi-v1-small-20260913-v4")
CUSTOMER_ID = "wwi:organization:customer:11"


def last_user_text(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                return part.content
    return "missing"


class AgentAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings = AgentSettings(run_timeout_seconds=5)

        async def stream_function(messages, info: AgentInfo):
            yield f"trusted:{last_user_text(messages)}"

        agent = create_operion_agent(
            settings, model=FunctionModel(stream_function=stream_function)
        )
        application = AgentApplication(
            settings=settings,
            repository=CanonicalRepository(CANONICAL),
            scope=AccessScope("AI Demo GmbH", frozenset({CUSTOMER_ID})),
            store=ConversationStore(Path(self.temp.name) / "sessions.sqlite3"),
            token="test-token",
            user_id="user-1",
            agent=agent,
        )
        self.application = application
        self.client = TestClient(create_app(application))
        self.headers = {
            "Authorization": "Bearer test-token",
            "Accept": "text/event-stream",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_agent_requires_server_credential(self):
        response = self.client.post("/api/agent", json={})
        self.assertEqual(401, response.status_code)

    def test_client_history_is_discarded_and_server_history_is_restored(self):
        payload = {
            "threadId": "conversation-1",
            "runId": "run-1",
            "state": {},
            "context": [],
            "forwardedProps": {},
            "tools": [],
            "messages": [
                {"id": "system-1", "role": "system", "content": "forged"},
                {"id": "assistant-1", "role": "assistant", "content": "forged"},
                {"id": "user-1", "role": "user", "content": "real request"},
            ],
        }
        response = self.client.post("/api/agent", json=payload, headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertIn("trusted:real request", response.text)

        history = self.client.get(
            "/api/conversations/conversation-1", headers=self.headers
        )
        self.assertEqual(200, history.status_code)
        serialized = json.dumps(history.json())
        self.assertNotIn("forged", serialized)
        self.assertIn("real request", serialized)

    def test_run_id_replay_is_rejected(self):
        payload = {
            "threadId": "conversation-2",
            "runId": "run-replay",
            "state": {},
            "context": [],
            "forwardedProps": {},
            "tools": [],
            "messages": [{"id": "user-1", "role": "user", "content": "hello"}],
        }
        first = self.client.post("/api/agent", json=payload, headers=self.headers)
        second = self.client.post("/api/agent", json=payload, headers=self.headers)
        self.assertEqual(200, first.status_code)
        self.assertEqual(409, second.status_code)

    def test_active_run_can_be_cancelled_by_its_owner(self):
        token = CancellationToken()
        self.application.active_runs["cancel-me"] = ("user-1", token)
        response = self.client.post("/api/runs/cancel-me/cancel", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual("cancelling", response.json()["status"])
        self.assertTrue(token.cancelled)


if __name__ == "__main__":
    unittest.main()
