"""Document-key restrictions apply before PostgreSQL candidate selection."""

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from knowledge.vectorstores.base import RetrievalFilter
from knowledge.vectorstores.pgvector import PgVectorStore


class PostgreSQLDocumentFilterTests(unittest.IsolatedAsyncioTestCase):
    def make_store(self):
        factory = MagicMock()
        session = AsyncMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        return PgVectorStore(factory, uuid.uuid4(), "fixture-model"), factory, session

    async def query_for(self, keys):
        store, _, session = self.make_store()
        await store.search(
            [1.0, 0.0],
            k=1,
            filters=RetrievalFilter(tenant_id="tenant-a", document_keys=keys),
        )
        return session.execute.await_args.args[0].compile()

    async def test_unrestricted_search_keeps_document_key_unrestricted(self):
        compiled = await self.query_for(None)
        self.assertNotIn("knowledge_documents.document_key IN", str(compiled))
        self.assertEqual(compiled.params["param_1"], 4)

    async def test_single_document_key_is_restricted_in_sql(self):
        compiled = await self.query_for({"requested-guide"})
        self.assertIn("knowledge_documents.document_key IN", str(compiled))
        self.assertIn(["requested-guide"], compiled.params.values())
        self.assertEqual(compiled.params["param_1"], 4)

    async def test_multiple_document_keys_are_restricted_in_sql(self):
        compiled = await self.query_for({"guide-b", "guide-a"})
        self.assertIn("knowledge_documents.document_key IN", str(compiled))
        self.assertIn(["guide-a", "guide-b"], compiled.params.values())

    async def test_empty_document_key_set_returns_without_querying(self):
        store, factory, session = self.make_store()
        self.assertEqual(
            await store.search(
                [1.0, 0.0],
                k=1,
                filters=RetrievalFilter(tenant_id="tenant-a", document_keys=set()),
            ),
            [],
        )
        factory.assert_not_called()
        session.execute.assert_not_awaited()

    async def test_chunk_and_document_are_both_restricted_to_store_organization(self):
        store, _, session = self.make_store()
        await store.search(
            [1.0, 0.0],
            k=1,
            filters=RetrievalFilter(tenant_id="fixture-tenant"),
        )
        statement = session.execute.await_args.args[0]
        compiled = statement.whereclause.compile()

        self.assertIn("knowledge_chunks.organization_id =", str(compiled))
        self.assertIn("knowledge_documents.organization_id =", str(compiled))
        organizations = [
            value for name, value in compiled.params.items() if name.startswith("organization_id")
        ]
        self.assertEqual(organizations, [store._org, store._org])
