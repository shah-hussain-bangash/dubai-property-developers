from __future__ import annotations

from datetime import date

import pytest

from core.exceptions.errors import DomainValidationError
from knowledge.documents.models import AccessLevel, DocumentStatus, SourceDocument
from knowledge.embeddings.base import HashingEmbeddingProvider
from knowledge.ingestion.chunking import chunk_text, normalize_text
from knowledge.ingestion.loaders import load_document
from knowledge.ingestion.pipeline import IngestionPipeline
from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter

T = "tenant-a"


def _setup() -> tuple[IngestionPipeline, Retriever, InMemoryVectorStore]:
    embedder = HashingEmbeddingProvider(256)
    store = InMemoryVectorStore()
    return (
        IngestionPipeline(embedder, store, chunk_size=200, chunk_overlap=20),
        Retriever(embedder, store),
        store,
    )


def test_normalize_and_chunk_with_overlap() -> None:
    text = normalize_text("Line one-\nword   here.\r\n\n\n\nNext paragraph.")
    assert text == "Line oneword here.\n\nNext paragraph."
    chunks = chunk_text("Sentence. " * 100, chunk_size=100, overlap=10)
    assert len(chunks) > 5
    assert all(len(c) <= 100 for c in chunks)
    with pytest.raises(ValueError):
        chunk_text("x", chunk_size=10, overlap=10)


def test_loader_rejects_unsupported_types() -> None:
    assert load_document(b"hello", "text/plain") == "hello"
    with pytest.raises(DomainValidationError):
        load_document(b"\x00", "application/zip")


async def test_retrieval_is_permission_and_tenant_aware() -> None:
    pipeline, retriever, _ = _setup()
    await pipeline.ingest(
        SourceDocument(
            tenant_id=T,
            document_key="pub",
            title="Public",
            text="payment plan details for towers",
            access_level=AccessLevel.PUBLIC,
        )
    )
    await pipeline.ingest(
        SourceDocument(
            tenant_id=T,
            document_key="secret",
            title="Restricted",
            text="payment plan commission split",
            access_level=AccessLevel.RESTRICTED,
            allowed_roles=["admin"],
        )
    )
    await pipeline.ingest(
        SourceDocument(
            tenant_id="other",
            document_key="x",
            title="Other tenant",
            text="payment plan other tenant",
            access_level=AccessLevel.PUBLIC,
        )
    )

    customer = await retriever.retrieve("payment plan", RetrievalFilter(tenant_id=T))
    assert {h.chunk.document_key for h in customer.hits} == {"pub"}

    staff_no_role = RetrievalFilter(tenant_id=T, access_levels=set(AccessLevel))
    assert "secret" not in {
        h.chunk.document_key for h in (await retriever.retrieve("payment plan", staff_no_role)).hits
    }

    admin = RetrievalFilter(tenant_id=T, access_levels=set(AccessLevel), principal_roles={"admin"})
    assert "secret" in {
        h.chunk.document_key for h in (await retriever.retrieve("payment plan", admin)).hits
    }


async def test_new_version_supersedes_old_and_stale_is_flagged() -> None:
    pipeline, retriever, _ = _setup()
    base = {
        "tenant_id": T,
        "document_key": "plan",
        "title": "Plan",
        "access_level": AccessLevel.PUBLIC,
    }
    await pipeline.ingest(SourceDocument(**base, version=1, text="old payment plan 20 percent"))
    report = await pipeline.ingest(
        SourceDocument(
            **base, version=2, text="new payment plan 10 percent", review_by=date(2020, 1, 1)
        )
    )
    assert report.superseded_chunks >= 1
    result = await retriever.retrieve(
        "payment plan", RetrievalFilter(tenant_id=T), today=date(2026, 1, 1)
    )
    assert {h.chunk.version for h in result.hits} == {2}
    assert result.has_stale
    assert result.citations()[0].version == 2
    history = await retriever.retrieve(
        "payment plan", RetrievalFilter(tenant_id=T, include_superseded=True)
    )
    assert any(h.chunk.status == DocumentStatus.SUPERSEDED for h in history.hits)


async def test_hashing_embeddings_are_deterministic_and_normalized() -> None:
    emb = HashingEmbeddingProvider(64)
    [a], [b] = (
        await emb.embed(["Dubai Marina apartment"]),
        await emb.embed(["Dubai Marina apartment"]),
    )
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
