"""Conversation memory keeps caller edits separate from saved history and state."""

import unittest

from core.memory.base import InMemoryConversationMemory, MemoryMessage


class ConversationSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.memory = InMemoryConversationMemory()

    async def test_input_message_changes_do_not_rewrite_saved_history(self):
        message = MemoryMessage(role="customer", content="Original", channel="web")
        await self.memory.append("fixture", message)
        message.content = "Changed outside memory"
        message.role = "system"
        message.channel = "email"
        [saved] = await self.memory.history("fixture")
        self.assertEqual(
            (saved.role, saved.content, saved.channel), ("customer", "Original", "web")
        )

    async def test_returned_message_changes_do_not_rewrite_saved_history(self):
        await self.memory.append("fixture", MemoryMessage(role="customer", content="Original"))
        [first] = await self.memory.history("fixture")
        first.content = "Changed history result"
        [second] = await self.memory.history("fixture")
        self.assertEqual(second.content, "Original")
        self.assertIsNot(first, second)

    async def test_input_nested_message_metadata_is_detached(self):
        message = MemoryMessage(
            role="customer", content="Original", metadata={"details": {"labels": ["original"]}}
        )
        await self.memory.append("fixture", message)
        message.metadata["details"]["labels"].append("changed")
        [saved] = await self.memory.history("fixture")
        self.assertEqual(saved.metadata["details"]["labels"], ["original"])

    async def test_returned_nested_message_metadata_is_detached(self):
        await self.memory.append(
            "fixture",
            MemoryMessage(
                role="customer", content="Original", metadata={"details": {"labels": ["original"]}}
            ),
        )
        [first] = await self.memory.history("fixture")
        first.metadata["details"]["labels"].append("changed")
        [second] = await self.memory.history("fixture")
        self.assertEqual(second.metadata["details"]["labels"], ["original"])

    async def test_input_nested_state_is_detached(self):
        state = {"preferences": {"areas": ["fictional-area"]}}
        await self.memory.set_state("fixture", state)
        state["preferences"]["areas"].append("changed")
        self.assertEqual(
            await self.memory.get_state("fixture"),
            {"preferences": {"areas": ["fictional-area"]}},
        )

    async def test_returned_nested_state_is_detached(self):
        await self.memory.set_state("fixture", {"progress": {"steps": ["original"]}})
        first = await self.memory.get_state("fixture")
        first["progress"]["steps"].append("changed")
        second = await self.memory.get_state("fixture")
        self.assertEqual(second, {"progress": {"steps": ["original"]}})

    async def test_shared_input_message_is_independent_between_conversations(self):
        message = MemoryMessage(role="customer", content="Original")
        await self.memory.append("first", message)
        message.content = "Second snapshot"
        await self.memory.append("second", message)
        [first] = await self.memory.history("first")
        [second] = await self.memory.history("second")
        self.assertEqual(first.content, "Original")
        self.assertEqual(second.content, "Second snapshot")

    async def test_explicit_state_updates_still_replace_saved_state(self):
        await self.memory.set_state("fixture", {"progress": {"steps": ["original"]}})
        update = await self.memory.get_state("fixture")
        update["progress"]["steps"].append("updated")
        await self.memory.set_state("fixture", update)
        self.assertEqual(
            await self.memory.get_state("fixture"),
            {"progress": {"steps": ["original", "updated"]}},
        )

    async def test_unknown_conversation_state_is_an_independent_empty_dict(self):
        state = await self.memory.get_state("missing")
        state["changed"] = True
        self.assertEqual(await self.memory.get_state("missing"), {})
