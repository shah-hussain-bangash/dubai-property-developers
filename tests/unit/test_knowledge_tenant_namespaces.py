"""Knowledge chunks with the same ID remain independent across tenants."""

import unittest

from knowledge.documents.models import AccessLevel, Chunk, DocumentStatus
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_chunk(tenant, chunk_id="shared", content="Original", **updates):
    values = {
        "tenant_id": tenant,
        "chunk_id": chunk_id,
        "document_id": "fictional-guide-v1",
        "document_key": "guide",
        "version": 1,
        "title": "Fictional guide",
        "chunk_index": 0,
        "content": content,
        "access_level": AccessLevel.PUBLIC,
    }
    values.update(updates)
    return Chunk(**values)


class KnowledgeTenantNamespaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryVectorStore()

    async def hits(self, tenant, **filters):
        return await self.store.search(
            [1.0, 0.0], k=10, filters=RetrievalFilter(tenant_id=tenant, **filters)
        )

    async def assert_content(self, tenant, expected):
        hits = await self.hits(tenant)
        self.assertEqual([hit.chunk.content for hit in hits], expected)
        self.assertTrue(all(hit.chunk.tenant_id == tenant for hit in hits))

    async def test_one_batch_preserves_same_id_for_two_tenants(self):
        await self.store.upsert(
            [fixture_chunk("tenant-a", content="A"), fixture_chunk("tenant-b", content="B")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        await self.assert_content("tenant-a", ["A"])
        await self.assert_content("tenant-b", ["B"])

    async def test_later_tenant_write_does_not_overwrite_existing_tenant(self):
        await self.store.upsert([fixture_chunk("tenant-a", content="A")], [[1.0, 0.0]])
        await self.store.upsert([fixture_chunk("tenant-b", content="B")], [[1.0, 0.0]])
        await self.assert_content("tenant-a", ["A"])
        await self.assert_content("tenant-b", ["B"])

    async def test_replacement_updates_only_the_matching_tenant_and_id(self):
        await self.store.upsert(
            [fixture_chunk("tenant-a", content="A"), fixture_chunk("tenant-b", content="B")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        await self.store.upsert([fixture_chunk("tenant-a", content="Updated A")], [[1.0, 0.0]])
        await self.assert_content("tenant-a", ["Updated A"])
        await self.assert_content("tenant-b", ["B"])

    async def test_superseding_is_scoped_to_tenant_even_with_colliding_ids(self):
        await self.store.upsert(
            [fixture_chunk("tenant-a"), fixture_chunk("tenant-b")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        self.assertEqual(await self.store.mark_superseded("tenant-a", "guide", 2), 1)
        await self.assert_content("tenant-a", [])
        await self.assert_content("tenant-b", ["Original"])
        [old] = await self.hits("tenant-a", include_superseded=True)
        self.assertEqual(old.chunk.status, DocumentStatus.SUPERSEDED)
        self.assertEqual(await self.store.mark_superseded("tenant-a", "guide", 2), 0)

    async def test_namespace_components_cannot_collide_through_delimiters(self):
        await self.store.upsert(
            [fixture_chunk("a:b", "c", "First"), fixture_chunk("a", "b:c", "Second")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        await self.assert_content("a:b", ["First"])
        await self.assert_content("a", ["Second"])

    async def test_failed_batch_preserves_all_tenant_records(self):
        await self.store.upsert(
            [fixture_chunk("tenant-a", content="A"), fixture_chunk("tenant-b", content="B")],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        with self.assertRaises(ValueError):
            await self.store.upsert(
                [fixture_chunk("tenant-a", content="Changed"), fixture_chunk("tenant-b")],
                [[1.0, 0.0]],
            )
        await self.assert_content("tenant-a", ["A"])
        await self.assert_content("tenant-b", ["B"])

    async def test_permission_filters_remain_independent_for_colliding_ids(self):
        await self.store.upsert(
            [
                fixture_chunk("tenant-a", content="Public A"),
                fixture_chunk(
                    "tenant-b",
                    content="Restricted B",
                    access_level=AccessLevel.RESTRICTED,
                    allowed_roles=["manager"],
                ),
            ],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        await self.assert_content("tenant-a", ["Public A"])
        await self.assert_content("tenant-b", [])
        [restricted] = await self.hits(
            "tenant-b", access_levels={AccessLevel.RESTRICTED}, principal_roles={"manager"}
        )
        self.assertEqual(restricted.chunk.content, "Restricted B")
        self.assertEqual(restricted.chunk.tenant_id, "tenant-b")

    async def test_tie_ordering_within_a_tenant_remains_deterministic(self):
        await self.store.upsert(
            [
                fixture_chunk("tenant-a", "z"),
                fixture_chunk("tenant-b", "a"),
                fixture_chunk("tenant-a", "a"),
            ],
            [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
        )
        self.assertEqual([hit.chunk.chunk_id for hit in await self.hits("tenant-a")], ["a", "z"])
