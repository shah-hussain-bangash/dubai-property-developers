"""pgvector-backed vector search (requires PostgreSQL with the ``vector`` extension).

Search uses cosine distance against ``chunk_embeddings`` joined to chunks and
documents so tenant, status and access filters are applied in SQL. Restricted-role
and metadata filters are applied in Python on the over-fetched candidate set.
Covered only by integration tests (``RUN_INTEGRATION_TESTS=1``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.knowledge import ChunkEmbedding, KnowledgeChunk, KnowledgeDocument
from knowledge.documents.models import AccessLevel, Chunk, DocumentStatus, ScoredChunk
from knowledge.vectorstores.base import RetrievalFilter


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

    async def search(self, vector: list[float], *, k: int, filters: RetrievalFilter) -> list[ScoredChunk]:
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
            .order_by(distance)
            .limit(k * 4)
        )
        if not filters.include_superseded:
            stmt = stmt.where(KnowledgeDocument.status == DocumentStatus.ACTIVE.value)
        async with self._factory() as session:
            rows = (await session.execute(stmt)).all()
        results: list[ScoredChunk] = []
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
        return results[:k]

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
            return int(result.rowcount or 0)
