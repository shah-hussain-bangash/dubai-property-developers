"""pgvector-backed vector search (requires PostgreSQL with the ``vector`` extension).

Search uses cosine distance against ``chunk_embeddings`` joined to chunks and
documents so tenant, status, access and restricted-role filters are applied in SQL.
Metadata filters are applied in Python while paging through bounded candidate batches.
Query filtering is covered by unit tests. Database execution requires
integration tests (``RUN_INTEGRATION_TESTS=1``).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.knowledge import ChunkEmbedding, KnowledgeChunk, KnowledgeDocument
from knowledge.documents.models import AccessLevel, Chunk, DocumentStatus, ScoredChunk
from knowledge.vectorstores.base import RetrievalFilter, validate_search_limit


class PgVectorStore:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
        embedding_model: str,
    ) -> None:
        self._factory = factory
        self._org = organization_id
        self._model = embedding_model

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        raise NotImplementedError(
            "Persisted ingestion writes knowledge_documents/knowledge_chunks/chunk_embeddings; "
            "planned for the next phase (see docs/development/roadmap.md)."
        )

    async def search(
        self, vector: list[float], *, k: int, filters: RetrievalFilter
    ) -> list[ScoredChunk]:
        validate_search_limit(k)
        if k == 0 or filters.document_keys == set():
            return []
        filters = filters.model_copy(deep=True)
        vector = list(vector)
        distance = ChunkEmbedding.embedding.cosine_distance(vector)
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == KnowledgeChunk.id)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeChunk.organization_id == self._org,
                ChunkEmbedding.embedding_model == self._model,
                KnowledgeDocument.access_level.in_([a.value for a in filters.access_levels]),
            )
            .order_by(distance, KnowledgeChunk.id)
            .limit(k * 4)
        )
        statuses = [DocumentStatus.ACTIVE.value]
        if filters.include_superseded:
            statuses.append(DocumentStatus.SUPERSEDED.value)
        stmt = stmt.where(KnowledgeDocument.status.in_(statuses))
        if filters.document_keys is not None:
            stmt = stmt.where(KnowledgeDocument.document_key.in_(sorted(filters.document_keys)))
        stmt = stmt.where(
            or_(
                KnowledgeDocument.access_level != AccessLevel.RESTRICTED.value,
                *(
                    KnowledgeDocument.allowed_roles.cast(JSONB).contains([role])
                    for role in sorted(filters.principal_roles)
                ),
            )
        )
        results: list[ScoredChunk] = []
        page = stmt
        async with self._factory() as session:
            while True:
                rows = (await session.execute(page)).all()
                for chunk_row, doc, dist in rows:
                    chunk = Chunk(
                        chunk_id=str(chunk_row.id),
                        tenant_id=filters.tenant_id,
                        document_id=str(doc.id),
                        document_key=doc.document_key,
                        version=doc.version,
                        title=doc.title,
                        chunk_index=chunk_row.chunk_index,
                        content=chunk_row.content,
                        access_level=AccessLevel(doc.access_level),
                        allowed_roles=list(doc.allowed_roles),
                        status=DocumentStatus(doc.status),
                        review_by=doc.review_by,
                        metadata=dict(chunk_row.attributes),
                    )
                    if filters.allows(chunk):
                        results.append(ScoredChunk(chunk=chunk, score=1.0 - float(dist)))
                        if len(results) == k:
                            return results
                if len(rows) < k * 4:
                    return results
                last_chunk, _, last_distance = rows[-1]
                page = stmt.where(
                    or_(
                        distance > last_distance,
                        and_(distance == last_distance, KnowledgeChunk.id > last_chunk.id),
                    )
                )

    async def mark_superseded(self, tenant_id: str, document_key: str, below_version: int) -> int:
        async with self._factory() as session, session.begin():
            result = await session.execute(
                update(KnowledgeDocument)
                .where(
                    KnowledgeDocument.organization_id == self._org,
                    KnowledgeDocument.document_key == document_key,
                    KnowledgeDocument.version < below_version,
                    KnowledgeDocument.status == DocumentStatus.ACTIVE.value,
                )
                .values(status=DocumentStatus.SUPERSEDED.value)
            )
            return int(cast(CursorResult[Any], result).rowcount or 0)
