"""Missing metadata must not match a literal string representation of None."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from knowledge.documents.models import AccessLevel, Chunk
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


def fixture_chunk(chunk_id="fixture", metadata=None):
    return Chunk(
        chunk_id=chunk_id,
        tenant_id="tenant-a",
        document_id="fictional-guide",
        document_key="guide",
        version=1,
        title="Fictional guide",
        chunk_index=0,
        content="Fictional knowledge",
        access_level=AccessLevel.PUBLIC,
        metadata=metadata or {},
    )


class MetadataPresenceTests(unittest.TestCase):
    def test_missing_field_does_not_match_literal_none(self):
        filters = RetrievalFilter(tenant_id="tenant-a", metadata_equals={"section": "None"})
        self.assertFalse(filters.allows(fixture_chunk()))

    def test_present_values_keep_existing_string_comparison_behavior(self):
        for value, expected in (("None", "None"), (None, "None"), (12, "12"), (True, "True")):
            with self.subTest(value=value):
                filters = RetrievalFilter(
                    tenant_id="tenant-a", metadata_equals={"section": expected}
                )
                self.assertTrue(filters.allows(fixture_chunk(metadata={"section": value})))

    def test_every_requested_field_must_exist_and_match(self):
        filters = RetrievalFilter(
            tenant_id="tenant-a", metadata_equals={"section": "None", "language": "en"}
        )
        self.assertFalse(filters.allows(fixture_chunk(metadata={"language": "en"})))
        self.assertFalse(
            filters.allows(fixture_chunk(metadata={"section": "None", "language": "ar"}))
        )
        self.assertTrue(
            filters.allows(fixture_chunk(metadata={"section": "None", "language": "en"}))
        )

    def test_empty_metadata_filter_remains_unrestricted(self):
        self.assertTrue(RetrievalFilter(tenant_id="tenant-a").allows(fixture_chunk()))


class MemoryMetadataPresenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_present_matching_metadata_is_returned(self):
        store = InMemoryVectorStore()
        await store.upsert(
            [fixture_chunk("missing"), fixture_chunk("present", {"section": "None"})],
            [[1.0, 0.0], [1.0, 0.0]],
        )
        hits = await store.search(
            [1.0, 0.0],
            k=10,
            filters=RetrievalFilter(tenant_id="tenant-a", metadata_equals={"section": "None"}),
        )
        self.assertEqual([hit.chunk.chunk_id for hit in hits], ["present"])


class PostgreSQLMetadataPresenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_rows_with_missing_metadata_are_excluded(self):
        from knowledge.vectorstores.pgvector import PgVectorStore

        organization_id = uuid.uuid4()
        present_id = uuid.uuid4()
        document = SimpleNamespace(
            id=uuid.uuid4(),
            document_key="guide",
            version=1,
            title="Fictional guide",
            access_level="public",
            allowed_roles=[],
            status="active",
            review_by=None,
        )
        rows = [
            (
                SimpleNamespace(
                    id=chunk_id, chunk_index=0, content="Fictional knowledge", attributes=metadata
                ),
                document,
                0.0,
            )
            for chunk_id, metadata in (
                (uuid.uuid4(), {}),
                (present_id, {"section": "None"}),
            )
        ]
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        result = MagicMock()
        result.all.return_value = rows
        session.execute.return_value = result
        store = PgVectorStore(factory, organization_id, "fixture-model")
        hits = await store.search(
            [1.0, 0.0],
            k=2,
            filters=RetrievalFilter(
                tenant_id=str(organization_id), metadata_equals={"section": "None"}
            ),
        )
        self.assertEqual([hit.chunk.chunk_id for hit in hits], [str(present_id)])
