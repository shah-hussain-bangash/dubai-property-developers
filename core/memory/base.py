"""Conversation memory interfaces.

``InMemoryConversationMemory`` serves tests and local demos. The database-backed
implementation lives in ``database/repositories/conversation_memory.py`` to keep
``core`` free of persistence dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class MemoryMessage(BaseModel):
    role: str  # "customer", "agent", "staff", "system"
    content: str
    channel: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


def validate_history_limit(limit: int) -> None:
    """Require a non-negative message count; zero requests no history."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("history limit must be a non-negative integer")


class ConversationMemory(Protocol):
    async def append(self, conversation_id: str, message: MemoryMessage) -> None: ...

    async def history(self, conversation_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        """Return up to limit recent messages in chronological order; zero returns none."""
        ...

    async def get_state(self, conversation_id: str) -> dict[str, Any]: ...

    async def set_state(self, conversation_id: str, state: dict[str, Any]) -> None: ...


class InMemoryConversationMemory:
    def __init__(self) -> None:
        self._messages: dict[str, list[MemoryMessage]] = defaultdict(list)
        self._state: dict[str, dict[str, Any]] = {}

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        self._messages[conversation_id].append(message.model_copy(deep=True))

    async def history(self, conversation_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        validate_history_limit(limit)
        if limit == 0:
            return []
        return [
            message.model_copy(deep=True)
            for message in self._messages.get(conversation_id, [])[-limit:]
        ]

    async def get_state(self, conversation_id: str) -> dict[str, Any]:
        return deepcopy(self._state.get(conversation_id, {}))

    async def set_state(self, conversation_id: str, state: dict[str, Any]) -> None:
        self._state[conversation_id] = deepcopy(state)
