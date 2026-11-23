"""Permission-aware retrieval with source attribution and staleness flags."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from knowledge.documents.models import ScoredChunk
from knowledge.embeddings.base import EmbeddingProvider
from knowledge.vectorstores.base import RetrievalFilter, VectorStore, validate_search_limit
from schemas.conversations.models import Citation


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: str
    hits: list[ScoredChunk]

    @property
    def top_score(self) -> float:
        return self.hits[0].score if self.hits else 0.0

    @property
    def has_stale(self) -> bool:
        return any(h.stale for h in self.hits)

    def citations(self, excerpt_chars: int = 240) -> list[Citation]:
        return [
            Citation(
                document_id=h.chunk.document_id,
                title=h.chunk.title,
                version=h.chunk.version,
                chunk_id=h.chunk.chunk_id,
                excerpt=h.chunk.content[:excerpt_chars],
            )
            for h in self.hits
        ]


class Retriever:
    def __init__(self, embedder: EmbeddingProvider, store: VectorStore, *, min_score: float = 0.05):
        self._embedder = embedder
        self._store = store
        self._min_score = min_score

    async def retrieve(
        self, query: str, filters: RetrievalFilter, *, k: int = 4, today: date | None = None
    ) -> RetrievalResult:
        validate_search_limit(k)
        if k == 0:
            return RetrievalResult(query=query, hits=[])
        filters = filters.model_copy(deep=True)
        [vector] = await self._embedder.embed([query])
        hits = await self._store.search(vector, k=k, filters=filters)
        current = today or date.today()
        flagged = [
            h.model_copy(update={"stale": bool(h.chunk.review_by and h.chunk.review_by < current)})
            for h in hits
            if h.score >= self._min_score
        ]
        return RetrievalResult(query=query, hits=flagged)
