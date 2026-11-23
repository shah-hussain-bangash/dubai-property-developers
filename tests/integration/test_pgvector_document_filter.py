"""A requested document remains searchable behind nearer unrelated documents."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.config.settings import get_settings
from database.models.identity import Organization
from database.models.knowledge import (
    EMBEDDING_DIMENSION,
    ChunkEmbedding,
    KnowledgeChunk,
    KnowledgeDocument,
)
from database.sessions.engine import create_engine
from knowledge.vectorstores.base import RetrievalFilter
from knowledge.vectorstores.pgvector import PgVectorStore
from tests.factories import integration_enabled

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not integration_enabled(), reason="Set RUN_INTEGRATION_TESTS=1"),
]


async def test_requested_document_survives_nearer_unrelated_candidates():
    settings = get_settings()
    if not settings.is_dev_like:
        pytest.skip("Knowledge search tests require a development database")
    engine = create_engine(settings)
    organization_id = uuid.uuid4()
    model = "fixture-document-filter"
    query = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMENSION - 2)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                factory = async_sessionmaker(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                async with factory() as session, session.begin():
                    session.add(
                        Organization(
                            id=organization_id,
                            name="Fictional Knowledge Filter Test",
                            slug=f"knowledge-filter-{organization_id.hex}",
                            is_active=True,
                        )
                    )
                    await session.flush()
                    for index in range(5):
                        requested = index == 4
                        document_id, chunk_id = uuid.uuid4(), uuid.uuid4()
                        key = "requested-guide" if requested else f"unrelated-{index}"
                        session.add(
                            KnowledgeDocument(
                                id=document_id,
                                organization_id=organization_id,
                                document_key=key,
                                version=1,
                                title="Fictional guide",
                                mime_type="text/plain",
                                status="active",
                                access_level="public",
                                allowed_roles=[],
                                content_hash="fixture",
                                attributes={},
                            )
                        )
                        await session.flush()
                        session.add(
                            KnowledgeChunk(
                                id=chunk_id,
                                organization_id=organization_id,
                                document_id=document_id,
                                chunk_index=0,
                                content="Fictional knowledge",
                                token_count=2,
                                content_hash="fixture",
                                attributes={},
                            )
                        )
                        await session.flush()
                        session.add(
                            ChunkEmbedding(
                                chunk_id=chunk_id,
                                embedding_model=model,
                                dimension=EMBEDDING_DIMENSION,
                                embedding=(
                                    [0.8, 0.6] + [0.0] * (EMBEDDING_DIMENSION - 2)
                                    if requested
                                    else query
                                ),
                            )
                        )
                store = PgVectorStore(factory, organization_id, model)
                unrestricted = await store.search(
                    query, k=1, filters=RetrievalFilter(tenant_id=str(organization_id))
                )
                assert unrestricted[0].chunk.document_key.startswith("unrelated-")
                hits = await store.search(
                    query,
                    k=1,
                    filters=RetrievalFilter(
                        tenant_id=str(organization_id), document_keys={"requested-guide"}
                    ),
                )
                assert len(hits) == 1
                assert hits[0].chunk.document_key == "requested-guide"
                assert hits[0].score == pytest.approx(0.8, abs=1e-6)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
