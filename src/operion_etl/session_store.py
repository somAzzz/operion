from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


class SessionAccessDenied(RuntimeError):
    pass


class RunReplayError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _message_id(prefix: str, index: int, content: str) -> str:
    digest = hashlib.sha256(f"{index}:{content}".encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _json_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def public_messages(messages: Sequence[ModelMessage]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message_index, message in enumerate(messages):
        if isinstance(message, ModelRequest):
            for part_index, part in enumerate(message.parts):
                index = message_index * 100 + part_index
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    result.append(
                        {
                            "id": _message_id("user", index, part.content),
                            "role": "user",
                            "content": part.content,
                        }
                    )
                elif isinstance(part, ToolReturnPart):
                    content = _json_content(part.content)
                    result.append(
                        {
                            "id": _message_id("tool", index, content),
                            "role": "tool",
                            "content": content,
                            "toolCallId": part.tool_call_id,
                            **(
                                {"error": part.outcome}
                                if part.outcome != "success"
                                else {}
                            ),
                        }
                    )
        elif isinstance(message, ModelResponse):
            text = "".join(
                part.content for part in message.parts if isinstance(part, TextPart)
            )
            tool_calls = [
                {
                    "id": part.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": part.tool_name,
                        "arguments": (
                            part.args
                            if isinstance(part.args, str)
                            else json.dumps(part.args or {}, ensure_ascii=False)
                        ),
                    },
                }
                for part in message.parts
                if isinstance(part, ToolCallPart)
            ]
            if text or tool_calls:
                seed = text + json.dumps(tool_calls, sort_keys=True)
                result.append(
                    {
                        "id": _message_id("assistant", message_index, seed),
                        "role": "assistant",
                        "content": text,
                        **({"toolCalls": tool_calls} if tool_calls else {}),
                    }
                )
    return result


class ConversationStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    messages_json BLOB NOT NULL DEFAULT '[]',
                    public_messages_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tool_calls_json TEXT NOT NULL DEFAULT '[]',
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_conversation
                    ON agent_runs(conversation_id, started_at);
                """
            )

    def get_or_create(self, conversation_id: str, owner_id: str) -> None:
        now = _now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT owner_id FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row is not None and row["owner_id"] != owner_id:
                raise SessionAccessDenied("conversation belongs to another user")
            if row is None:
                connection.execute(
                    """
                    INSERT INTO conversations(
                        conversation_id, owner_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (conversation_id, owner_id, now, now),
                )

    def history(self, conversation_id: str, owner_id: str) -> list[ModelMessage]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT owner_id, messages_json FROM conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            return []
        if row["owner_id"] != owner_id:
            raise SessionAccessDenied("conversation belongs to another user")
        return ModelMessagesTypeAdapter.validate_json(row["messages_json"])

    def public_history(
        self, conversation_id: str, owner_id: str
    ) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT owner_id, public_messages_json FROM conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            return []
        if row["owner_id"] != owner_id:
            raise SessionAccessDenied("conversation belongs to another user")
        return json.loads(row["public_messages_json"])

    def save_history(
        self,
        conversation_id: str,
        owner_id: str,
        messages: Sequence[ModelMessage],
    ) -> None:
        serialized = ModelMessagesTypeAdapter.dump_json(messages)
        public = json.dumps(public_messages(messages), ensure_ascii=False)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET messages_json = ?, public_messages_json = ?, updated_at = ?
                WHERE conversation_id = ? AND owner_id = ?
                """,
                (serialized, public, _now(), conversation_id, owner_id),
            )
            if cursor.rowcount != 1:
                raise SessionAccessDenied("conversation owner changed")

    def start_run(
        self,
        run_id: str,
        conversation_id: str,
        owner_id: str,
        model_name: str,
    ) -> None:
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO agent_runs(
                        run_id, conversation_id, owner_id, model_name,
                        status, started_at
                    ) VALUES (?, ?, ?, ?, 'running', ?)
                    """,
                    (run_id, conversation_id, owner_id, model_name, _now()),
                )
        except sqlite3.IntegrityError as error:
            raise RunReplayError("run_id was already used") from error

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        tool_calls: Sequence[dict[str, Any]],
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_code: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_runs SET
                    status = ?, tool_calls_json = ?, input_tokens = ?,
                    output_tokens = ?, error_code = ?, completed_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    json.dumps(tool_calls, ensure_ascii=False, default=str),
                    input_tokens,
                    output_tokens,
                    error_code,
                    _now(),
                    run_id,
                ),
            )

    def run(self, run_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        if row["owner_id"] != owner_id:
            raise SessionAccessDenied("run belongs to another user")
        result = dict(row)
        result["tool_calls"] = json.loads(result.pop("tool_calls_json"))
        return result
