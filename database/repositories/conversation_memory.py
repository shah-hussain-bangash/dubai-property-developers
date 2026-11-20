"""Database-backed ``ConversationMemory`` (conversations + messages tables).

Requires PostgreSQL; covered by integration tests (``RUN_INTEGRATION_TESTS=1``).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.memory.base import MemoryMessage
from database.models.conversation import Conversation, Message

_ROLE_TO_SENDER = {
    "customer": "customer",
    "agent": "ai_agent",
    "staff": "staff",
    "system": "system",
}


class SqlConversationMemory:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
    ) -> None:
        self._factory = factory
        self._org = organization_id

    async def _conversation(self, session: AsyncSession, conversation_id: str) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.id == uuid.UUID(conversation_id), Conversation.organization_id == self._org
        )
        conversation = (await session.execute(stmt)).scalar_one_or_none()
        if conversation is None:
            raise LookupError(f"conversation {conversation_id} not found")
        return conversation

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
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
                    attributes=message.metadata,
                    sent_at=message.created_at,
                )
            )
            if message.role == "customer":
                conversation.last_inbound_at = message.created_at

    async def history(self, conversation_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        async with self._factory() as session:
            stmt = (
                select(Message)
                .where(
                    Message.conversation_id == uuid.UUID(conversation_id),
                    Message.organization_id == self._org,
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
                metadata=row.attributes,
            )
            for row in reversed(rows)
        ]

    async def get_state(self, conversation_id: str) -> dict[str, Any]:
        async with self._factory() as session:
            return dict((await self._conversation(session, conversation_id)).state)

    async def set_state(self, conversation_id: str, state: dict[str, Any]) -> None:
        async with self._factory() as session, session.begin():
            conversation = await self._conversation(session, conversation_id)
            conversation.state = dict(state)
