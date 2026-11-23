"""Conversation history limits agree across memory and database implementations."""

import unittest
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from core.memory.base import InMemoryConversationMemory, MemoryMessage

INVALID_LIMITS = (-1, -20, True, False, 1.5, "2", None)


class InMemoryHistoryLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.memory = InMemoryConversationMemory()
        for index in range(25):
            await self.memory.append("fixture", MemoryMessage(role="customer", content=str(index)))

    async def test_zero_returns_no_messages_from_populated_history(self):
        self.assertEqual(await self.memory.history("fixture", limit=0), [])

    async def test_invalid_limits_fail_with_a_clear_error(self):
        for limit in INVALID_LIMITS:
            with (
                self.subTest(limit=limit),
                self.assertRaisesRegex(ValueError, "non-negative integer"),
            ):
                await self.memory.history("fixture", limit=limit)

    async def test_positive_limit_returns_latest_messages_in_chronological_order(self):
        history = await self.memory.history("fixture", limit=3)
        self.assertEqual([message.content for message in history], ["22", "23", "24"])

    async def test_default_limit_remains_twenty_messages(self):
        history = await self.memory.history("fixture")
        self.assertEqual([message.content for message in history], [str(n) for n in range(5, 25)])

    async def test_large_limit_returns_all_available_messages(self):
        self.assertEqual(len(await self.memory.history("fixture", limit=100)), 25)

    async def test_unknown_conversation_has_no_history(self):
        self.assertEqual(await self.memory.history("missing"), [])
        self.assertEqual(await self.memory.history("missing", limit=0), [])


class DatabaseHistoryLimitTests(unittest.IsolatedAsyncioTestCase):
    def make_memory(self):
        from database.repositories.conversation_memory import SqlConversationMemory

        factory = MagicMock()
        organization_id = uuid.uuid4()
        return SqlConversationMemory(factory, organization_id), factory, organization_id

    async def test_zero_returns_no_messages_without_opening_a_session(self):
        memory, factory, _ = self.make_memory()
        self.assertEqual(await memory.history(str(uuid.uuid4()), limit=0), [])
        factory.assert_not_called()

    async def test_invalid_limits_fail_before_opening_a_session(self):
        memory, factory, _ = self.make_memory()
        for limit in INVALID_LIMITS:
            with (
                self.subTest(limit=limit),
                self.assertRaisesRegex(ValueError, "non-negative integer"),
            ):
                await memory.history(str(uuid.uuid4()), limit=limit)
        factory.assert_not_called()

    async def test_positive_limit_preserves_query_scope_and_chronological_results(self):
        memory, factory, organization_id = self.make_memory()
        conversation_id = uuid.uuid4()
        session = AsyncMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        result = MagicMock()
        result.scalars.return_value = [
            SimpleNamespace(
                direction="inbound",
                body=body,
                channel="web",
                sent_at=datetime(2026, 1, day, tzinfo=UTC),
                attributes={},
            )
            for day, body in ((3, "latest"), (2, "previous"))
        ]
        session.execute.return_value = result
        history = await memory.history(str(conversation_id), limit=2)
        self.assertEqual([message.content for message in history], ["previous", "latest"])
        statement = session.execute.await_args.args[0]
        compiled = statement.compile(compile_kwargs={"literal_binds": True})
        self.assertIn("LIMIT 2", str(compiled))
        self.assertIn("messages.sent_at DESC", str(compiled))
        params = statement.compile().params
        self.assertIn(conversation_id, params.values())
        self.assertIn(organization_id, params.values())
