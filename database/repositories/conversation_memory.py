"""Database-backed ``ConversationMemory`` (conversations + messages tables).

Requires PostgreSQL; covered by integration tests (``RUN_INTEGRATION_TESTS=1``).
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.exceptions.errors import AuthorizationError
from core.memory.base import MemoryMessage, validate_history_limit
from database.models.conversation import Conversation, Message

_ROLE_TO_SENDER = {
    "customer": "customer",
    "agent": "ai_agent",
    "staff": "staff",
    "system": "system",
}

AGENT_FIELD = "_agent_memory_owner_v1"
STATE_FIELD = "_agent_memory_states_v1"


class SqlConversationMemory:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
        *,
        agent_id: str | None = None,
    ) -> None:
        self._factory = factory
        self._org = organization_id
        self._agent = agent_id

    def scoped(self, tenant_id: str, agent_id: str) -> SqlConversationMemory:
        try:
            matches = uuid.UUID(tenant_id) == self._org
        except ValueError:
            matches = False
        if not matches or (self._agent is not None and self._agent != agent_id):
            raise AuthorizationError("Memory belongs to a different organization or agent")
        return SqlConversationMemory(self._factory, self._org, agent_id=agent_id)

    async def _conversation(
        self, session: AsyncSession, conversation_id: str, *, lock: bool = False
    ) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.id == uuid.UUID(conversation_id), Conversation.organization_id == self._org
        )
        if lock:
            stmt = stmt.with_for_update()
        conversation = (await session.execute(stmt)).scalar_one_or_none()
        if conversation is None:
            raise LookupError(f"conversation {conversation_id} not found")
        return conversation

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        attributes = deepcopy(message.metadata)
        attributes.pop(AGENT_FIELD, None)
        if self._agent is not None:
            attributes[AGENT_FIELD] = self._agent
        async with self._factory() as session, session.begin():
            conversation = await self._conversation(session, conversation_id)
            session.add(
                Message(
                    organization_id=self._org,
                    conversation_id=conversation.id,
                    direction="inbound" if message.role == "customer" else "outbound",
                    channel=message.channel or conversation.channel,
                    sender_type=_ROLE_TO_SENDER.get(message.role, "system"),
                    body=message.content,
                    attributes=attributes,
                    sent_at=message.created_at,
                )
            )
            if message.role == "customer":
                conversation.last_inbound_at = message.created_at

    async def history(self, conversation_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        validate_history_limit(limit)
        if limit == 0:
            return []
        async with self._factory() as session:
            owner = Message.attributes[AGENT_FIELD].as_string()
            stmt = (
                select(Message)
                .where(
                    Message.conversation_id == uuid.UUID(conversation_id),
                    Message.organization_id == self._org,
                    owner.is_(None) if self._agent is None else owner == self._agent,
                )
                .order_by(Message.sent_at.desc())
                .limit(limit)
            )
            rows = list((await session.execute(stmt)).scalars())
        return [
            MemoryMessage(
                role="customer" if row.direction == "inbound" else "agent",
                content=row.body,
                channel=row.channel,
                created_at=row.sent_at,
                metadata={
                    key: value for key, value in row.attributes.items() if key != AGENT_FIELD
                },
            )
            for row in reversed(rows)
        ]

    async def get_state(self, conversation_id: str) -> dict[str, Any]:
        async with self._factory() as session:
            state = dict((await self._conversation(session, conversation_id)).state)
        if self._agent is None:
            state.pop(STATE_FIELD, None)
            return deepcopy(state)
        if state and STATE_FIELD not in state:
            raise AuthorizationError("Legacy conversation state requires explicit ownership review")
        scopes = state.get(STATE_FIELD, {})
        value = scopes.get(self._agent, {}) if isinstance(scopes, dict) else {}
        return deepcopy(value) if isinstance(value, dict) else {}

    async def set_state(self, conversation_id: str, state: dict[str, Any]) -> None:
        async with self._factory() as session, session.begin():
            conversation = await self._conversation(session, conversation_id, lock=True)
            existing = dict(conversation.state)
            scopes = existing.get(STATE_FIELD, {})
            scopes = deepcopy(scopes) if isinstance(scopes, dict) else {}
            if self._agent is None:
                updated = deepcopy(state)
                updated.pop(STATE_FIELD, None)
                if scopes:
                    updated[STATE_FIELD] = scopes
            else:
                if existing and STATE_FIELD not in existing:
                    raise AuthorizationError(
                        "Legacy conversation state requires explicit ownership review"
                    )
                updated = deepcopy(existing)
                scopes[self._agent] = deepcopy(state)
                updated[STATE_FIELD] = scopes
            conversation.state = updated
