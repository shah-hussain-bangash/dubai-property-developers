"""Including superseded versions must never reintroduce archived knowledge."""

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from knowledge.documents.models import AccessLevel, Chunk, DocumentStatus
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_chunk(status, **updates):
    values = {
        "chunk_id": status.value,
        "tenant_id": "tenant-a",
        "document_id": "fictional-guide",
        "document_key": "guide",
        "version": 1,
        "title": "Fictional guide",
        "chunk_index": 0,
        "content": "Fictional knowledge",
        "access_level": AccessLevel.PUBLIC,
        "status": status,
    }
    values.update(updates)
    return Chunk(**values)


class KnowledgeStatusFilterTests(unittest.TestCase):
    def test_active_documents_are_allowed_in_both_modes(self):
        for include in (False, True):
            with self.subTest(include=include):
                filters = RetrievalFilter(tenant_id="tenant-a", include_superseded=include)
                self.assertTrue(filters.allows(fixture_chunk(DocumentStatus.ACTIVE)))

    def test_superseded_documents_require_explicit_inclusion(self):
        chunk = fixture_chunk(DocumentStatus.SUPERSEDED)
        self.assertFalse(RetrievalFilter(tenant_id="tenant-a").allows(chunk))
        filters = RetrievalFilter(tenant_id="tenant-a", include_superseded=True)
        self.assertTrue(filters.allows(chunk))

    def test_archived_documents_are_excluded_in_both_modes(self):
        for include in (False, True):
            with self.subTest(include=include):
                filters = RetrievalFilter(tenant_id="tenant-a", include_superseded=include)
                self.assertFalse(filters.allows(fixture_chunk(DocumentStatus.ARCHIVED)))

    def test_superseded_inclusion_preserves_tenant_and_role_checks(self):
        filters = RetrievalFilter(
            tenant_id="tenant-a",
            include_superseded=True,
            access_levels=set(AccessLevel),
            principal_roles={"staff"},
        )
        self.assertFalse(
            filters.allows(fixture_chunk(DocumentStatus.SUPERSEDED, tenant_id="tenant-b"))
        )
        self.assertFalse(
            filters.allows(
                fixture_chunk(
                    DocumentStatus.SUPERSEDED,
                    access_level=AccessLevel.RESTRICTED,
                    allowed_roles=["manager"],
                )
            )
        )


class InMemoryKnowledgeStatusTests(unittest.IsolatedAsyncioTestCase):
    async def make_store(self):
        store = InMemoryVectorStore()
        await store.upsert(
            [fixture_chunk(status) for status in DocumentStatus],
            [[1.0, 0.0] for _ in DocumentStatus],
        )
        return store

    async def test_default_search_returns_active_only(self):
        store = await self.make_store()
        hits = await store.search([1.0, 0.0], k=10, filters=RetrievalFilter(tenant_id="tenant-a"))
        self.assertEqual([hit.chunk.status for hit in hits], [DocumentStatus.ACTIVE])

    async def test_history_search_returns_active_and_superseded_without_archived(self):
        store = await self.make_store()
        hits = await store.search(
            [1.0, 0.0],
            k=10,
            filters=RetrievalFilter(tenant_id="tenant-a", include_superseded=True),
        )
        self.assertEqual(
            {hit.chunk.status for hit in hits},
            {DocumentStatus.ACTIVE, DocumentStatus.SUPERSEDED},
        )


class PostgreSQLKnowledgeStatusTests(unittest.IsolatedAsyncioTestCase):
    async def query_for(self, include):
        from knowledge.vectorstores.pgvector import PgVectorStore

        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        store = PgVectorStore(factory, uuid.uuid4(), "fixture-model")
        self.assertEqual(
            await store.search(
                [1.0, 0.0],
                k=2,
                filters=RetrievalFilter(tenant_id="tenant-a", include_superseded=include),
            ),
            [],
        )
        return session.execute.await_args.args[0]

    async def test_default_query_limits_status_before_candidate_selection(self):
        statement = await self.query_for(False)
        compiled = statement.compile()
        self.assertIn(["active"], compiled.params.values())
        self.assertIn("knowledge_documents.status IN", str(compiled))

    async def test_history_query_limits_status_before_candidate_selection(self):
        statement = await self.query_for(True)
        compiled = statement.compile()
        self.assertIn(["active", "superseded"], compiled.params.values())
        self.assertIn("knowledge_documents.status IN", str(compiled))
