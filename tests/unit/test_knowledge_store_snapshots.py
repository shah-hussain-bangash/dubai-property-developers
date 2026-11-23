"""Knowledge-store callers cannot mutate persisted content, permissions, or vectors."""

import unittest

from knowledge.documents.models import AccessLevel, Chunk, DocumentStatus
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_chunk(**updates):
    values = {
        "chunk_id": "fixture",
        "tenant_id": "tenant-a",
        "document_id": "document-fixture",
        "document_key": "guide",
        "version": 1,
        "title": "Fictional guide",
        "chunk_index": 0,
        "content": "Original fictional content",
        "access_level": AccessLevel.PUBLIC,
        "metadata": {"details": {"labels": ["original"]}},
    }
    values.update(updates)
    return Chunk(**values)


class KnowledgeSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryVectorStore()
        self.filters = RetrievalFilter(tenant_id="tenant-a")

    async def search(self, filters=None):
        return await self.store.search([1.0, 0.0], k=10, filters=filters or self.filters)

    async def test_input_content_and_nested_metadata_are_detached(self):
        chunk = fixture_chunk()
        await self.store.upsert([chunk], [[1.0, 0.0]])
        chunk.content = "Changed outside the store"
        chunk.metadata["details"]["labels"].append("changed")
        [hit] = await self.search()
        self.assertEqual(hit.chunk.content, "Original fictional content")
        self.assertEqual(hit.chunk.metadata["details"]["labels"], ["original"])

    async def test_input_access_changes_cannot_publish_restricted_content(self):
        chunk = fixture_chunk(access_level=AccessLevel.RESTRICTED, allowed_roles=["manager"])
        await self.store.upsert([chunk], [[1.0, 0.0]])
        chunk.access_level = AccessLevel.PUBLIC
        self.assertEqual(await self.search(), [])

    async def test_input_role_changes_do_not_grant_access(self):
        chunk = fixture_chunk(access_level=AccessLevel.RESTRICTED, allowed_roles=["manager"])
        await self.store.upsert([chunk], [[1.0, 0.0]])
        chunk.allowed_roles.append("visitor")
        filters = RetrievalFilter(
            tenant_id="tenant-a",
            access_levels={AccessLevel.RESTRICTED},
            principal_roles={"visitor"},
        )
        self.assertEqual(await self.search(filters), [])

    async def test_input_tenant_changes_do_not_move_stored_content(self):
        chunk = fixture_chunk()
        await self.store.upsert([chunk], [[1.0, 0.0]])
        chunk.tenant_id = "tenant-b"
        self.assertEqual(await self.search(RetrievalFilter(tenant_id="tenant-b")), [])
        self.assertEqual(len(await self.search()), 1)

    async def test_input_vector_changes_do_not_change_ranking(self):
        vector = [1.0, 0.0]
        await self.store.upsert(
            [fixture_chunk(), fixture_chunk(chunk_id="runner-up")],
            [vector, [0.8, 0.6]],
        )
        vector[:] = [0.0, 1.0]
        hits = await self.search()
        self.assertEqual(hits[0].chunk.chunk_id, "fixture")
        self.assertAlmostEqual(hits[0].score, 1.0)

    async def test_search_result_changes_do_not_change_later_searches(self):
        await self.store.upsert([fixture_chunk()], [[1.0, 0.0]])
        [first] = await self.search()
        first.chunk.content = "Changed search result"
        first.chunk.metadata["details"]["labels"].append("changed")
        first.chunk.status = DocumentStatus.ARCHIVED
        [second] = await self.search()
        self.assertEqual(second.chunk.content, "Original fictional content")
        self.assertEqual(second.chunk.metadata["details"]["labels"], ["original"])
        self.assertEqual(second.chunk.status, DocumentStatus.ACTIVE)

    async def test_authorized_search_result_cannot_grant_another_role_access(self):
        chunk = fixture_chunk(access_level=AccessLevel.RESTRICTED, allowed_roles=["manager"])
        await self.store.upsert([chunk], [[1.0, 0.0]])
        filters = RetrievalFilter(
            tenant_id="tenant-a",
            access_levels={AccessLevel.RESTRICTED},
            principal_roles={"manager"},
        )
        [hit] = await self.search(filters)
        hit.chunk.allowed_roles.append("visitor")
        filters.principal_roles = {"visitor"}
        self.assertEqual(await self.search(filters), [])

    async def test_explicit_upsert_still_updates_existing_content(self):
        chunk = fixture_chunk()
        await self.store.upsert([chunk], [[1.0, 0.0]])
        chunk.content = "Explicit replacement"
        await self.store.upsert([chunk], [[1.0, 0.0]])
        [hit] = await self.search()
        self.assertEqual(hit.chunk.content, "Explicit replacement")

    async def test_superseding_preserves_previously_returned_snapshots(self):
        await self.store.upsert([fixture_chunk()], [[1.0, 0.0]])
        [previous] = await self.search()
        self.assertEqual(await self.store.mark_superseded("tenant-a", "guide", 2), 1)
        self.assertEqual(await self.search(), [])
        [current] = await self.search(
            RetrievalFilter(tenant_id="tenant-a", include_superseded=True)
        )
        self.assertEqual(current.chunk.status, DocumentStatus.SUPERSEDED)
        self.assertEqual(previous.chunk.status, DocumentStatus.ACTIVE)
