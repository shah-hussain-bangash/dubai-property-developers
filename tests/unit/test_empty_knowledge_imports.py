"""Empty knowledge imports cannot supersede useful document content."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.exceptions.errors import DomainValidationError
from knowledge.documents.models import AccessLevel, DocumentStatus, SourceDocument
from knowledge.ingestion.pipeline import IngestionPipeline
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_document(text, *, version=1):
    return SourceDocument(
        tenant_id="tenant-a",
        document_key="guide",
        version=version,
        title="Fictional guide",
        text=text,
        access_level=AccessLevel.PUBLIC,
    )


class EmptyKnowledgeImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_blank_imports_fail_before_embedding_or_store_calls(self):
        embedder = SimpleNamespace(embed=AsyncMock())
        store = SimpleNamespace(upsert=AsyncMock(), mark_superseded=AsyncMock())
        pipeline = IngestionPipeline(embedder, store)
        for text in ("", " \n\t\r ", "\u00a0\u3000"):
            with (
                self.subTest(text=text),
                self.assertRaisesRegex(DomainValidationError, "no text"),
            ):
                await pipeline.ingest(fixture_document(text))
        embedder.embed.assert_not_awaited()
        store.upsert.assert_not_awaited()
        store.mark_superseded.assert_not_awaited()

    async def test_empty_new_version_preserves_previous_active_document(self):
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        store = InMemoryVectorStore()
        pipeline = IngestionPipeline(embedder, store)
        original = await pipeline.ingest(fixture_document("Original fictional content"))
        with self.assertRaises(DomainValidationError):
            await pipeline.ingest(fixture_document(" \n\t ", version=2))
        hits = await store.search([1.0, 0.0], k=10, filters=RetrievalFilter(tenant_id="tenant-a"))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.document_id, original.document_id)
        self.assertEqual(hits[0].chunk.version, 1)
        self.assertEqual(hits[0].chunk.status, DocumentStatus.ACTIVE)
        self.assertEqual(hits[0].chunk.content, "Original fictional content")
        self.assertEqual(embedder.embed.await_count, 1)

    async def test_surrounding_whitespace_in_valid_document_is_still_normalized(self):
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        store = InMemoryVectorStore()
        pipeline = IngestionPipeline(embedder, store)
        report = await pipeline.ingest(fixture_document("  Fictional   content.\r\n "))
        self.assertEqual(report.chunks, 1)
        self.assertEqual(report.superseded_chunks, 0)
        embedder.embed.assert_awaited_once_with(["Fictional content."])
        [hit] = await store.search([1.0, 0.0], k=10, filters=RetrievalFilter(tenant_id="tenant-a"))
        self.assertEqual(hit.chunk.content, "Fictional content.")

    async def test_nonempty_new_version_still_supersedes_the_previous_version(self):
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        store = InMemoryVectorStore()
        pipeline = IngestionPipeline(embedder, store)
        await pipeline.ingest(fixture_document("Original fictional content"))
        report = await pipeline.ingest(fixture_document("Updated fictional content", version=2))
        self.assertEqual(report.chunks, 1)
        self.assertEqual(report.superseded_chunks, 1)
        [hit] = await store.search([1.0, 0.0], k=10, filters=RetrievalFilter(tenant_id="tenant-a"))
        self.assertEqual(hit.chunk.version, 2)
        self.assertEqual(hit.chunk.content, "Updated fictional content")
