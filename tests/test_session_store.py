import tempfile
import unittest
from datetime import UTC, datetime, timedelta
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

    def test_expired_raw_content_is_scrubbed_but_access_audit_is_immutable(self):
        self.store.get_or_create("conversation-retention", "user-1")
        self.store.save_history(
            "conversation-retention",
            "user-1",
            [ModelRequest(parts=[UserPromptPart(content="sensitive")])],
        )
        self.store.record_access(
            "user-1", "conversation", "conversation-retention", "read_history"
        )
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (
                    (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                    "conversation-retention",
                ),
            )
        result = self.store.purge_content(datetime.now(UTC) - timedelta(days=1))
        self.assertEqual(1, result["conversations_scrubbed"])
        self.assertEqual(
            [], self.store.public_history("conversation-retention", "user-1")
        )
        with self.assertRaises(Exception):
            with self.store._connect() as connection:
                connection.execute("DELETE FROM access_events")

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

    def test_conversation_list_is_scoped_titled_and_recent_first(self):
        self.store.get_or_create("older", "user-1")
        self.store.save_history(
            "older",
            "user-1",
            [ModelRequest(parts=[UserPromptPart("  First   customer inquiry  ")])],
        )
        self.store.get_or_create("newer", "user-1")
        self.store.save_history(
            "newer",
            "user-1",
            [ModelRequest(parts=[UserPromptPart("Second inquiry")])],
        )
        self.store.get_or_create("other-user", "user-2")

        conversations = self.store.list_conversations("user-1")

        self.assertEqual(
            ["newer", "older"],
            [row["conversation_id"] for row in conversations],
        )
        self.assertEqual("Second inquiry", conversations[0]["title"])
        self.assertEqual("First customer inquiry", conversations[1]["title"])
        self.assertEqual(1, conversations[0]["message_count"])

    def test_conversation_delete_is_owned_and_audited(self):
        self.store.get_or_create("delete-me", "user-1")
        self.store.save_history(
            "delete-me",
            "user-1",
            [ModelRequest(parts=[UserPromptPart("remove this history")])],
        )
        self.store.get_or_create("keep-me", "user-2")

        with self.assertRaises(SessionAccessDenied):
            self.store.delete_conversation("keep-me", "user-1")
        self.assertTrue(self.store.delete_conversation("delete-me", "user-1"))
        self.assertFalse(self.store.delete_conversation("delete-me", "user-1"))
        self.assertEqual([], self.store.public_history("delete-me", "user-1"))
        with self.store._connect() as connection:
            audit = connection.execute(
                """
                SELECT operation, outcome FROM access_events
                WHERE resource_id = 'delete-me'
                """
            ).fetchone()
        self.assertEqual("delete_history", audit["operation"])
        self.assertEqual("allowed", audit["outcome"])


if __name__ == "__main__":
    unittest.main()
