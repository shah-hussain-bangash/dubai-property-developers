from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Must match EMBEDDING_DIMENSION. Changing it requires a migration + re-embedding.
EMBEDDING_DIMENSION = 1536


class KnowledgeDocument(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("organization_id", "document_key", "version"),)

    # Logical identity shared by all versions of the same document.
    document_key: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(300))
    source_uri: Mapped[str | None] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="active")
    access_level: Mapped[str] = mapped_column(String(32), default="internal")
    allowed_roles: Mapped[list[str]] = mapped_column(default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_by: Mapped[date | None] = mapped_column(Date)  # past this date = stale
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)


class KnowledgeChunk(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ChunkEmbedding(UUIDPrimaryKeyMixin, Base):
    """Embedding vector + metadata. One row per (chunk, embedding model)."""

    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "embedding_model"),
        Index(
            "ix_chunk_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), index=True
    )
    embedding_model: Mapped[str] = mapped_column(String(100))
    dimension: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
