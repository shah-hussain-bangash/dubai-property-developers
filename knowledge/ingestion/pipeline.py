"""Ingestion pipeline: normalize -> chunk -> embed -> store, with versioning."""

from __future__ import annotations

from dataclasses import dataclass

from core.exceptions.errors import DomainValidationError
from knowledge.documents.models import Chunk, SourceDocument
from knowledge.embeddings.base import EmbeddingProvider
from knowledge.ingestion.chunking import chunk_text, normalize_text
from knowledge.vectorstores.base import VectorStore


@dataclass(frozen=True, slots=True)
class IngestionReport:
    document_id: str
    chunks: int
    superseded_chunks: int


class IngestionPipeline:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: VectorStore,
        *,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._chunk_size = chunk_size
        self._overlap = chunk_overlap

    async def ingest(self, document: SourceDocument) -> IngestionReport:
        text = normalize_text(document.text)
        pieces = chunk_text(text, chunk_size=self._chunk_size, overlap=self._overlap)
        if not pieces:
            raise DomainValidationError("Document has no text to ingest")
        chunks = [
            Chunk(
                chunk_id=f"{document.document_id}#{i}",
                tenant_id=document.tenant_id,
                document_id=document.document_id,
                document_key=document.document_key,
                version=document.version,
                title=document.title,
                chunk_index=i,
                content=piece,
                access_level=document.access_level,
                allowed_roles=document.allowed_roles,
                review_by=document.review_by,
                metadata={k: str(v) for k, v in document.metadata.items()},
            )
            for i, piece in enumerate(pieces)
        ]
        vectors = await self._embedder.embed([c.content for c in chunks])
        await self._store.upsert(chunks, vectors)
        superseded = await self._store.mark_superseded(
            document.tenant_id, document.document_key, below_version=document.version
        )
        return IngestionReport(document.document_id, len(chunks), superseded)
