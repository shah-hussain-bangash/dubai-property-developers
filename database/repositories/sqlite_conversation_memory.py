"""Optional local durable conversation memory with atomic SQLite state patches."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from core.memory.base import (
    ConversationMemory,
    MemoryMessage,
    ScopedConversationMemory,
    validate_history_limit,
)


class SqliteConversationMemory:
    def __init__(self, path: str) -> None:
        if path == ":memory:":
            raise ValueError("Durable memory requires a file path")
        self.path = Path(path).absolute()

    def scoped(self, tenant_id: str, agent_id: str) -> ConversationMemory:
        return ScopedConversationMemory(self, tenant_id, agent_id)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS memory_messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT NOT NULL, "
                "message TEXT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS memory_messages_conversation "
                "ON memory_messages(conversation,id)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS memory_states ("
                "conversation TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )
            return db
        except Exception:
            db.close()
            raise

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        with closing(self._connect()):
            pass

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        encoded = message.model_dump_json()
        await asyncio.to_thread(self._append, conversation_id, encoded)

    def _append(self, conversation_id: str, encoded: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO memory_messages(conversation,message) VALUES (?,?)",
                (conversation_id, encoded),
            )

    async def history(self, conversation_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        validate_history_limit(limit)
        if limit == 0:
            return []
        return await asyncio.to_thread(self._history, conversation_id, limit)

    def _history(self, conversation_id: str, limit: int) -> list[MemoryMessage]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT message FROM memory_messages WHERE conversation=? ORDER BY id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [MemoryMessage.model_validate_json(row[0]) for row in reversed(rows)]

    @staticmethod
    def _encode(state: dict[str, Any]) -> str:
        if not isinstance(state, dict):
            raise ValueError("Conversation state must be a JSON object")
        return json.dumps(state, allow_nan=False, ensure_ascii=False)

    @staticmethod
    def _read_state(db: sqlite3.Connection, conversation_id: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT state FROM memory_states WHERE conversation=?", (conversation_id,)
        ).fetchone()
        if row is None:
            return {}
        value = json.loads(row[0])
        if not isinstance(value, dict):
            raise ValueError("Stored conversation state must be a JSON object")
        return value

    async def get_state(self, conversation_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_state, conversation_id)

    def _get_state(self, conversation_id: str) -> dict[str, Any]:
        with closing(self._connect()) as db:
            return self._read_state(db, conversation_id)

    async def set_state(self, conversation_id: str, state: dict[str, Any]) -> None:
        encoded = self._encode(state)
        await asyncio.to_thread(self._set_state, conversation_id, encoded)

    def _set_state(self, conversation_id: str, encoded: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO memory_states(conversation,state) VALUES (?,?) "
                "ON CONFLICT(conversation) DO UPDATE SET state=excluded.state",
                (conversation_id, encoded),
            )

    async def update_state(self, conversation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        encoded = self._encode(patch)
        return await asyncio.to_thread(self._update_state, conversation_id, encoded)

    def _update_state(self, conversation_id: str, encoded: str) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            # Serialize read/merge/write across independently connected processes.
            db.execute("BEGIN IMMEDIATE")
            state = self._read_state(db, conversation_id)
            state.update(json.loads(encoded))
            db.execute(
                "INSERT INTO memory_states(conversation,state) VALUES (?,?) "
                "ON CONFLICT(conversation) DO UPDATE SET state=excluded.state",
                (conversation_id, self._encode(state)),
            )
        return state
