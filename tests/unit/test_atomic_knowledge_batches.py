"""Failed knowledge batches never leave partially written chunks."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from knowledge.documents.models import AccessLevel, Chunk, SourceDocument
from knowledge.ingestion.pipeline import IngestionPipeline
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_chunk(chunk_id, content="Original", version=1):
    return Chunk(
        chunk_id=chunk_id,
        tenant_id="tenant-a",
        document_id=f"guide-v{version}",
        document_key="guide",
        version=version,
        title="Fictional guide",
        chunk_index=0,
        content=content,
        access_level=AccessLevel.PUBLIC,
    )


class UncopyableFixture:
    def __deepcopy__(self, memo):
        raise RuntimeError("fixture snapshot failure")


class AtomicKnowledgeBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryVectorStore()
        await self.store.upsert([fixture_chunk("existing")], [[1.0, 0.0]])

    async def records(self):
        hits = await self.store.search(
            [1.0, 0.0],
            k=100,
            filters=RetrievalFilter(tenant_id="tenant-a", include_superseded=True),
        )
        return {hit.chunk.chunk_id: hit.chunk.content for hit in hits}

    async def test_missing_vector_does_not_insert_a_partial_batch(self):
        with self.assertRaises(ValueError):
            await self.store.upsert(
                [fixture_chunk("first"), fixture_chunk("second")], [[1.0, 0.0]]
            )
        self.assertEqual(await self.records(), {"existing": "Original"})

    async def test_extra_vector_does_not_replace_an_existing_record(self):
        with self.assertRaises(ValueError):
            await self.store.upsert(
                [fixture_chunk("existing", "Replacement")], [[1.0, 0.0], [0.0, 1.0]]
            )
        self.assertEqual(await self.records(), {"existing": "Original"})

    async def test_snapshot_failure_does_not_commit_earlier_replacements(self):
        broken = fixture_chunk("broken")
        broken.metadata["fixture"] = UncopyableFixture()
        with self.assertRaisesRegex(RuntimeError, "fixture snapshot failure"):
            await self.store.upsert(
                [fixture_chunk("existing", "Replacement"), broken],
                [[1.0, 0.0], [1.0, 0.0]],
            )
        self.assertEqual(await self.records(), {"existing": "Original"})

    async def test_valid_batch_inserts_and_replaces_together(self):
        await self.store.upsert(
            [fixture_chunk("existing", "Replacement"), fixture_chunk("new", "New")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        self.assertEqual(await self.records(), {"existing": "Replacement", "new": "New"})

    async def test_empty_batch_preserves_existing_records(self):
        await self.store.upsert([], [])
        self.assertEqual(await self.records(), {"existing": "Original"})

    async def test_duplicate_ids_preserve_last_write_behavior(self):
        await self.store.upsert(
            [fixture_chunk("new", "First"), fixture_chunk("new", "Last")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        self.assertEqual(await self.records(), {"existing": "Original", "new": "Last"})

    async def test_failed_ingestion_preserves_old_version_without_partial_new_chunks(self):
        embedder = SimpleNamespace(embed=AsyncMock(return_value=[[1.0, 0.0]]))
        pipeline = IngestionPipeline(embedder, self.store, chunk_size=50, chunk_overlap=5)
        document = SourceDocument(
            tenant_id="tenant-a",
            document_key="guide",
            version=2,
            title="Fictional guide",
            text="Fictional guide paragraph. " * 20,
            access_level=AccessLevel.PUBLIC,
        )
        with self.assertRaises(ValueError):
            await pipeline.ingest(document)
        self.assertEqual(await self.records(), {"existing": "Original"})
        active = await self.store.search(
            [1.0, 0.0], k=100, filters=RetrievalFilter(tenant_id="tenant-a")
        )
        self.assertEqual([hit.chunk.version for hit in active], [1])
        embedder.embed.assert_awaited_once()
