"""Search inputs remain stable across asynchronous embedding and database calls."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from knowledge.documents.models import AccessLevel, Chunk
from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_chunk(tenant):
    return Chunk(
        chunk_id=tenant,
        tenant_id=tenant,
        document_id="fictional-guide",
        document_key="guide",
        version=1,
        title="Fictional guide",
        chunk_index=0,
        content="Fictional knowledge",
        access_level=AccessLevel.RESTRICTED,
        allowed_roles=["manager"],
        metadata={"section": "wanted"},
    )


def fixture_row(index=1, *, section="wanted", restricted=False):
    return (
        SimpleNamespace(
            id=uuid.UUID(int=index),
            chunk_index=0,
            content="Fictional knowledge",
            attributes={"section": section},
        ),
        SimpleNamespace(
            id=uuid.UUID(int=100),
            document_key="guide",
            version=1,
            title="Fictional guide",
            access_level="restricted" if restricted else "public",
            allowed_roles=["manager"] if restricted else [],
            status="active",
            review_by=None,
        ),
        0.0,
    )


class RetrieverInputSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_filter_edits_during_embedding_do_not_change_the_search(self):
        store = InMemoryVectorStore()
        await store.upsert(
            [fixture_chunk("tenant-a"), fixture_chunk("tenant-b")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        filters = RetrievalFilter(
            tenant_id="tenant-a",
            access_levels={AccessLevel.RESTRICTED},
            principal_roles={"manager"},
            document_keys={"guide"},
            metadata_equals={"section": "wanted"},
        )

        async def embed(texts):
            filters.tenant_id = "tenant-b"
            filters.access_levels.clear()
            filters.principal_roles.clear()
            filters.document_keys.clear()
            filters.metadata_equals["section"] = "changed"
            return [[1.0, 0.0]]

        result = await Retriever(SimpleNamespace(embed=embed), store).retrieve("fixture", filters)
        self.assertEqual([hit.chunk.tenant_id for hit in result.hits], ["tenant-a"])

    async def test_explicit_later_search_still_uses_updated_filter(self):
        store = InMemoryVectorStore()
        await store.upsert(
            [fixture_chunk("tenant-a"), fixture_chunk("tenant-b")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        filters = RetrievalFilter(
            tenant_id="tenant-a",
            access_levels={AccessLevel.RESTRICTED},
            principal_roles={"manager"},
        )
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        retriever = Retriever(embedder, store)
        first = await retriever.retrieve("fixture", filters)
        filters.tenant_id = "tenant-b"
        second = await retriever.retrieve("fixture", filters)
        self.assertEqual([hit.chunk.tenant_id for hit in first.hits], ["tenant-a"])
        self.assertEqual([hit.chunk.tenant_id for hit in second.hits], ["tenant-b"])


class PostgreSQLInputSnapshotTests(unittest.IsolatedAsyncioTestCase):
    def make_store(self, execute):
        from knowledge.vectorstores.pgvector import PgVectorStore

        session = AsyncMock()
        session.execute.side_effect = execute
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        return PgVectorStore(factory, uuid.uuid4(), "fixture-model"), session

    @staticmethod
    def result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    async def test_tenant_edits_during_query_do_not_relabel_results(self):
        filters = RetrievalFilter(tenant_id="tenant-a")

        async def execute(statement):
            filters.tenant_id = "tenant-b"
            return self.result([fixture_row()])

        store, _ = self.make_store(execute)
        hits = await store.search([1.0, 0.0], k=1, filters=filters)
        self.assertEqual([hit.chunk.tenant_id for hit in hits], ["tenant-a"])

    async def test_collection_edits_during_query_do_not_change_permission_or_metadata_checks(self):
        filters = RetrievalFilter(
            tenant_id="tenant-a",
            access_levels={AccessLevel.RESTRICTED},
            principal_roles={"manager"},
            document_keys={"guide"},
            metadata_equals={"section": "wanted"},
        )

        async def execute(statement):
            filters.access_levels.clear()
            filters.principal_roles.clear()
            filters.document_keys.clear()
            filters.metadata_equals["section"] = "changed"
            return self.result([fixture_row(restricted=True)])

        store, _ = self.make_store(execute)
        hits = await store.search([1.0, 0.0], k=1, filters=filters)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.metadata, {"section": "wanted"})

    async def test_vector_edits_during_query_do_not_change_later_candidate_pages(self):
        vector = [1.0, 0.0]
        vectors = []

        async def execute(statement):
            params = statement.compile().params
            bound = next(
                value
                for value in params.values()
                if isinstance(value, list) and value and isinstance(value[0], float)
            )
            vectors.append(list(bound))
            if len(vectors) == 1:
                vector[:] = [0.0, 1.0]
                return self.result([fixture_row(i, section="other") for i in range(1, 5)])
            return self.result([fixture_row(5)])

        store, session = self.make_store(execute)
        hits = await store.search(
            vector,
            k=1,
            filters=RetrievalFilter(tenant_id="tenant-a", metadata_equals={"section": "wanted"}),
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(session.execute.await_count, 2)
        self.assertEqual(vectors, [[1.0, 0.0], [1.0, 0.0]])
