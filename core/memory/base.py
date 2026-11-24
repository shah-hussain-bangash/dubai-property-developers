"""Conversation memory interfaces.

``InMemoryConversationMemory`` serves tests and local demos. The database-backed
implementation lives in ``database/repositories/conversation_memory.py`` to keep
``core`` free of persistence dependencies.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from core.exceptions.errors import AuthorizationError


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

    async def update_state(self, conversation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Atomically merge top-level fields and return an independent resulting snapshot."""
        ...


@runtime_checkable
class ScopedMemoryProvider(Protocol):
    def scoped(self, tenant_id: str, agent_id: str) -> ConversationMemory: ...


class ScopedConversationMemory:
    """An isolated view over a string-keyed memory backend."""

    def __init__(self, memory: ConversationMemory, tenant_id: str, agent_id: str) -> None:
        self._memory = memory
        self._tenant = tenant_id
        self._agent = agent_id

    def scoped(self, tenant_id: str, agent_id: str) -> ConversationMemory:
        if (tenant_id, agent_id) != (self._tenant, self._agent):
            raise AuthorizationError("Memory belongs to a different organization or agent")
        return self

    def _key(self, conversation_id: str) -> str:
        identity = json.dumps([self._tenant, self._agent, conversation_id])
        return "agent-memory:v1:" + hashlib.sha256(identity.encode()).hexdigest()

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        await self._memory.append(self._key(conversation_id), message)

    async def history(self, conversation_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        return await self._memory.history(self._key(conversation_id), limit=limit)

    async def get_state(self, conversation_id: str) -> dict[str, Any]:
        return await self._memory.get_state(self._key(conversation_id))

    async def set_state(self, conversation_id: str, state: dict[str, Any]) -> None:
        await self._memory.set_state(self._key(conversation_id), state)

    async def update_state(self, conversation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return await self._memory.update_state(self._key(conversation_id), patch)


class InMemoryConversationMemory:
    def __init__(self) -> None:
        self._messages: dict[str, list[MemoryMessage]] = defaultdict(list)
        self._state: dict[str, dict[str, Any]] = {}

    def scoped(self, tenant_id: str, agent_id: str) -> ConversationMemory:
        return ScopedConversationMemory(self, tenant_id, agent_id)

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

    async def update_state(self, conversation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        # No await before assignment: one atomic patch on the process-local event loop.
        state = deepcopy(self._state.get(conversation_id, {}))
        state.update(deepcopy(patch))
        self._state[conversation_id] = state
        return deepcopy(state)
