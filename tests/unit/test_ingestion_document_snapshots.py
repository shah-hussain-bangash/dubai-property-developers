"""An import keeps one document identity across asynchronous provider/store calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from knowledge.documents.models import AccessLevel, SourceDocument
from knowledge.ingestion.pipeline import IngestionPipeline
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_document(tenant="tenant-a", key="guide", version=1, text="Fictional content"):
    return SourceDocument(
        tenant_id=tenant,
        document_key=key,
        version=version,
        title="Fictional guide",
        text=text,
        access_level=AccessLevel.PUBLIC,
    )


class IngestionSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryVectorStore()
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        pipeline = IngestionPipeline(embedder, self.store)
        await pipeline.ingest(fixture_document())
        await pipeline.ingest(fixture_document("tenant-b", "other"))

    @staticmethod
    def change_identity(document):
        document.tenant_id = "tenant-b"
        document.document_key = "other"
        document.version = 99

    async def assert_versions(self, tenant, expected):
        hits = await self.store.search([1.0, 0.0], k=10, filters=RetrievalFilter(tenant_id=tenant))
        self.assertEqual(sorted(hit.chunk.version for hit in hits), expected)

    async def test_edits_during_embedding_cannot_change_superseding_scope(self):
        document = fixture_document(version=2)
        original_id = document.document_id

        async def embed(texts):
            self.change_identity(document)
            return [[1.0, 0.0] for _ in texts]

        pipeline = IngestionPipeline(SimpleNamespace(embed=embed), self.store)
        report = await pipeline.ingest(document)
        self.assertEqual(report.document_id, original_id)
        self.assertEqual(report.superseded_chunks, 1)
        await self.assert_versions("tenant-a", [2])
        await self.assert_versions("tenant-b", [1])

    async def test_edits_during_upsert_cannot_change_superseding_scope(self):
        document = fixture_document(version=2)
        original_id = document.document_id

        async def upsert(chunks, vectors):
            await self.store.upsert(chunks, vectors)
            self.change_identity(document)

        store = SimpleNamespace(upsert=upsert, mark_superseded=self.store.mark_superseded)
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        report = await IngestionPipeline(embedder, store).ingest(document)
        self.assertEqual(report.document_id, original_id)
        self.assertEqual(report.superseded_chunks, 1)
        await self.assert_versions("tenant-a", [2])
        await self.assert_versions("tenant-b", [1])

    async def test_edits_during_superseding_cannot_change_report_identity(self):
        document = fixture_document(version=2)
        original_id = document.document_id

        async def supersede(tenant, key, below_version):
            count = await self.store.mark_superseded(tenant, key, below_version)
            self.change_identity(document)
            return count

        store = SimpleNamespace(upsert=self.store.upsert, mark_superseded=supersede)
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        report = await IngestionPipeline(embedder, store).ingest(document)
        self.assertEqual(report.document_id, original_id)
        await self.assert_versions("tenant-a", [2])
        await self.assert_versions("tenant-b", [1])

    async def test_explicit_subsequent_import_still_uses_updated_input(self):
        document = fixture_document(version=2, text="  Second fictional version  ")
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        pipeline = IngestionPipeline(embedder, self.store)
        await pipeline.ingest(document)
        self.assertEqual(document.text, "  Second fictional version  ")
        document.version = 3
        document.text = "Third fictional version"
        report = await pipeline.ingest(document)
        self.assertEqual(report.document_id, document.document_id)
        self.assertEqual(report.superseded_chunks, 1)
        await self.assert_versions("tenant-a", [3])
        await self.assert_versions("tenant-b", [1])
