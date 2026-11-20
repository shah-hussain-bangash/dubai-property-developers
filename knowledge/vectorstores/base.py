"""Vector store contract, metadata filters and an in-memory implementation."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from knowledge.documents.models import AccessLevel, Chunk, DocumentStatus, ScoredChunk
from knowledge.embeddings.base import cosine


class RetrievalFilter(BaseModel):
    tenant_id: str
    access_levels: set[AccessLevel] = Field(default_factory=lambda: {AccessLevel.PUBLIC})
    principal_roles: set[str] = Field(default_factory=set)
    document_keys: set[str] | None = None
    metadata_equals: dict[str, str] = Field(default_factory=dict)
    include_superseded: bool = False

    def allows(self, chunk: Chunk) -> bool:
        if chunk.tenant_id != self.tenant_id:
            return False
        if not self.include_superseded and chunk.status != DocumentStatus.ACTIVE:
            return False
        if chunk.access_level not in self.access_levels:
            return False
        if chunk.access_level == AccessLevel.RESTRICTED and not (
            set(chunk.allowed_roles) & self.principal_roles
        ):
            return False
        if self.document_keys is not None and chunk.document_key not in self.document_keys:
            return False
        return all(str(chunk.metadata.get(k)) == v for k, v in self.metadata_equals.items())


class VectorStore(Protocol):
    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

    async def search(self, vector: list[float], *, k: int, filters: RetrievalFilter) -> list[ScoredChunk]: ...

    async def mark_superseded(self, tenant_id: str, document_key: str, below_version: int) -> int: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[Chunk, list[float]]] = {}

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._items[chunk.chunk_id] = (chunk, vector)

    async def search(self, vector: list[float], *, k: int, filters: RetrievalFilter) -> list[ScoredChunk]:
        scored = [
            ScoredChunk(chunk=chunk, score=cosine(vector, vec))
            for chunk, vec in self._items.values()
            if filters.allows(chunk)
        ]
        scored.sort(key=lambda s: (-s.score, s.chunk.chunk_id))
        return scored[:k]

    async def mark_superseded(self, tenant_id: str, document_key: str, below_version: int) -> int:
        count = 0
        for chunk_id, (chunk, vec) in list(self._items.items()):
            if (
                chunk.tenant_id == tenant_id
                and chunk.document_key == document_key
                and chunk.version < below_version
                and chunk.status == DocumentStatus.ACTIVE
            ):
                self._items[chunk_id] = (chunk.model_copy(update={"status": DocumentStatus.SUPERSEDED}), vec)
                count += 1
        return count
