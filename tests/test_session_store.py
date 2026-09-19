import tempfile
import unittest
from pathlib import Path

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from operion_etl.session_store import (
    ConversationStore,
    RunReplayError,
    SessionAccessDenied,
    public_messages,
)


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.temp.name) / "sessions.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_history_is_bound_to_server_authenticated_owner(self):
        self.store.get_or_create("conversation-1", "user-1")
        with self.assertRaises(SessionAccessDenied):
            self.store.get_or_create("conversation-1", "user-2")
        with self.assertRaises(SessionAccessDenied):
            self.store.public_history("conversation-1", "user-2")

    def test_run_ids_cannot_be_replayed(self):
        self.store.get_or_create("conversation-1", "user-1")
        self.store.start_run("run-1", "conversation-1", "user-1", "model")
        with self.assertRaises(RunReplayError):
            self.store.start_run("run-1", "conversation-1", "user-1", "model")

    def test_public_history_preserves_tool_call_and_result(self):
        messages = [
            ModelRequest(parts=[UserPromptPart("check F01")]),
            ModelResponse(
                parts=[ToolCallPart("check_fulfillment", {"case_id": "F01"}, "call-1")]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "check_fulfillment",
                        {"ok": True, "data": {"result": "satisfiable"}},
                        "call-1",
                    )
                ]
            ),
            ModelResponse(parts=[TextPart("可满足，但不是交付保证。")]),
        ]
        self.store.get_or_create("conversation-1", "user-1")
        self.store.save_history("conversation-1", "user-1", messages)
        restored = self.store.history("conversation-1", "user-1")
        public = self.store.public_history("conversation-1", "user-1")
        self.assertEqual(4, len(restored))
        self.assertEqual(public_messages(messages), public)
        self.assertEqual(
            "check_fulfillment", public[1]["toolCalls"][0]["function"]["name"]
        )
        self.assertEqual("tool", public[2]["role"])


if __name__ == "__main__":
    unittest.main()
