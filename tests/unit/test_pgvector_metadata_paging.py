"""Metadata filtering continues through ordered bounded PostgreSQL batches."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from knowledge.vectorstores.base import RetrievalFilter
from knowledge.vectorstores.pgvector import PgVectorStore


def fixture_row(index, *, matches=False, distance=0.0):
    return (
        SimpleNamespace(
            id=uuid.UUID(int=index),
            chunk_index=0,
            content="Fictional knowledge",
            attributes={"section": "wanted" if matches else "other"},
        ),
        SimpleNamespace(
            id=uuid.UUID(int=100),
            document_key="guide",
            version=1,
            title="Fictional guide",
            access_level="public",
            allowed_roles=[],
            status="active",
            review_by=None,
        ),
        distance,
    )


class PostgreSQLMetadataPagingTests(unittest.IsolatedAsyncioTestCase):
    async def search_pages(self, pages, *, k=1):
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        results = []
        for rows in pages:
            result = MagicMock()
            result.all.return_value = rows
            results.append(result)
        session.execute.side_effect = results
        store = PgVectorStore(factory, uuid.uuid4(), "fixture-model")
        hits = await store.search(
            [1.0, 0.0],
            k=k,
            filters=RetrievalFilter(tenant_id="tenant-a", metadata_equals={"section": "wanted"}),
        )
        return hits, session

    async def test_matching_result_beyond_first_batch_is_found(self):
        pages = [
            [fixture_row(index) for index in range(1, 5)],
            [fixture_row(5, matches=True, distance=0.2)],
        ]
        hits, session = await self.search_pages(pages)
        self.assertEqual([hit.chunk.chunk_id for hit in hits], [str(uuid.UUID(int=5))])
        self.assertAlmostEqual(hits[0].score, 0.8)
        self.assertEqual(session.execute.await_count, 2)

    async def test_exhausted_candidates_terminate_with_no_matches(self):
        pages = [[fixture_row(index) for index in range(1, 5)], []]
        hits, session = await self.search_pages(pages)
        self.assertEqual(hits, [])
        self.assertEqual(session.execute.await_count, 2)

    async def test_enough_results_stop_without_another_query(self):
        rows = [fixture_row(index, matches=True) for index in range(1, 5)]
        hits, session = await self.search_pages([rows])
        self.assertEqual(len(hits), 1)
        self.assertEqual(session.execute.await_count, 1)

    async def test_short_final_batch_stops_without_another_query(self):
        hits, session = await self.search_pages([[fixture_row(1)]])
        self.assertEqual(hits, [])
        self.assertEqual(session.execute.await_count, 1)

    async def test_next_page_uses_distance_and_id_cursor_with_deterministic_order(self):
        pages = [[fixture_row(index, distance=0.1) for index in range(1, 5)], []]
        _, session = await self.search_pages(pages)
        first, second = [call.args[0].compile() for call in session.execute.await_args_list]
        self.assertIn("ORDER BY", str(first))
        self.assertIn("knowledge_chunks.id", str(first).split("ORDER BY", 1)[1])
        self.assertIn(uuid.UUID(int=4), second.params.values())
        self.assertIn(0.1, second.params.values())
        self.assertIn("knowledge_chunks.id >", str(second))
        self.assertIn(4, second.params.values())

    async def test_requested_count_can_be_filled_across_batches(self):
        hits, session = await self.search_pages(
            [
                [fixture_row(index, matches=index == 8) for index in range(1, 9)],
                [fixture_row(9, matches=True, distance=0.2)],
            ],
            k=2,
        )
        expected = [str(uuid.UUID(int=8)), str(uuid.UUID(int=9))]
        self.assertEqual([hit.chunk.chunk_id for hit in hits], expected)
        self.assertEqual(session.execute.await_count, 2)
