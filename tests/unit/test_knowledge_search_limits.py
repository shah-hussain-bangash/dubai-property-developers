"""Search limits agree across retrieval, memory, and PostgreSQL entry points."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge.documents.models import AccessLevel, Chunk
from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter

INVALID_LIMITS = (-1, -20, True, False, 1.5, "2", None)


class MemorySearchLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryVectorStore()
        self.filters = RetrievalFilter(tenant_id="tenant-a")
        chunks = [
            Chunk(
                chunk_id=str(index),
                tenant_id="tenant-a",
                document_id="fictional-guide",
                document_key="guide",
                version=1,
                title="Fictional guide",
                chunk_index=index,
                content="Fictional knowledge",
                access_level=AccessLevel.PUBLIC,
            )
            for index in range(3)
        ]
        await self.store.upsert(chunks, [[1.0, 0.0] for _ in chunks])

    async def test_invalid_limits_are_rejected(self):
        for limit in INVALID_LIMITS:
            with (
                self.subTest(limit=limit),
                self.assertRaisesRegex(ValueError, "non-negative integer"),
            ):
                await self.store.search([1.0, 0.0], k=limit, filters=self.filters)

    async def test_zero_returns_empty_without_scoring(self):
        with patch("knowledge.vectorstores.base.cosine") as cosine:
            self.assertEqual(await self.store.search([1.0, 0.0], k=0, filters=self.filters), [])
        cosine.assert_not_called()

    async def test_positive_limit_preserves_result_count_and_order(self):
        hits = await self.store.search([1.0, 0.0], k=2, filters=self.filters)
        self.assertEqual([hit.chunk.chunk_id for hit in hits], ["0", "1"])


class RetrieverSearchLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        self.store = SimpleNamespace(search=AsyncMock(return_value=[]))
        self.retriever = Retriever(self.embedder, self.store)
        self.filters = RetrievalFilter(tenant_id="tenant-a")

    async def test_invalid_limits_fail_before_embedding_or_search(self):
        for limit in INVALID_LIMITS:
            with (
                self.subTest(limit=limit),
                self.assertRaisesRegex(ValueError, "non-negative integer"),
            ):
                await self.retriever.retrieve("fixture query", self.filters, k=limit)
        self.embedder.embed.assert_not_awaited()
        self.store.search.assert_not_awaited()

    async def test_zero_returns_complete_empty_result_without_embedding_or_search(self):
        result = await self.retriever.retrieve("fixture query", self.filters, k=0)
        self.assertEqual(result.query, "fixture query")
        self.assertEqual(result.hits, [])
        self.assertEqual(result.citations(), [])
        self.assertEqual(result.top_score, 0.0)
        self.assertFalse(result.has_stale)
        self.embedder.embed.assert_not_awaited()
        self.store.search.assert_not_awaited()

    async def test_default_limit_remains_four_and_positive_limits_are_forwarded(self):
        for limit in (None, 2):
            with self.subTest(limit=limit):
                self.embedder.embed.reset_mock()
                self.store.search.reset_mock()
                if limit is None:
                    await self.retriever.retrieve("fixture query", self.filters)
                else:
                    await self.retriever.retrieve("fixture query", self.filters, k=limit)
                self.embedder.embed.assert_awaited_once_with(["fixture query"])
                self.store.search.assert_awaited_once_with(
                    [1.0, 0.0], k=4 if limit is None else limit, filters=self.filters
                )


class PostgreSQLSearchLimitTests(unittest.IsolatedAsyncioTestCase):
    def make_store(self):
        from knowledge.vectorstores.pgvector import PgVectorStore

        factory = MagicMock()
        return PgVectorStore(factory, uuid.uuid4(), "fixture-model"), factory

    async def test_invalid_limits_fail_without_opening_a_session(self):
        store, factory = self.make_store()
        for limit in INVALID_LIMITS:
            with (
                self.subTest(limit=limit),
                self.assertRaisesRegex(ValueError, "non-negative integer"),
            ):
                await store.search(
                    [1.0, 0.0], k=limit, filters=RetrievalFilter(tenant_id="tenant-a")
                )
        factory.assert_not_called()

    async def test_zero_returns_empty_without_opening_a_session(self):
        store, factory = self.make_store()
        self.assertEqual(
            await store.search([1.0, 0.0], k=0, filters=RetrievalFilter(tenant_id="tenant-a")),
            [],
        )
        factory.assert_not_called()

    async def test_positive_limit_preserves_candidate_multiplier(self):
        store, factory = self.make_store()
        session = AsyncMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await store.search([1.0, 0.0], k=2, filters=RetrievalFilter(tenant_id="tenant-a"))
        statement = session.execute.await_args.args[0]
        self.assertEqual(statement.compile().params["param_1"], 8)
