"""Durable, tenant/agent-scoped supplied sources and extractive answers.

No model, demo corpus, external search or evaluation data is used to answer.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.exceptions.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PolicyViolationError,
)
from knowledge.ingestion.chunking import chunk_text
from knowledge.retrieval.source_terms import passage_terms, question_terms
from schemas.conversations.models import Citation

MAX_SOURCE_CHARS = 200_000
MAX_AGENT_CHARS = 2_000_000
MAX_AGENT_SOURCES = 100
NO_ANSWER = "I could not find an answer in this agent's supplied sources. Add a relevant source or ask a more specific question."


class AssignedSources:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE IF NOT EXISTS agent_sources ("
            "tenant TEXT NOT NULL, agent TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL, "
            "kind TEXT NOT NULL, uri TEXT, pages TEXT NOT NULL, chars INTEGER NOT NULL, "
            "created TEXT NOT NULL, review_by TEXT, customer_safe INTEGER NOT NULL, PRIMARY KEY(tenant, agent, id))"
        )
        return db

    def list_sources(self, tenant: str, agent: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id,title,kind,uri,chars,created,review_by,customer_safe FROM agent_sources "
                "WHERE tenant=? AND agent=? ORDER BY created DESC,id",
                (tenant, agent),
            ).fetchall()
        return [dict(row) for row in rows]

    def read_source(self, tenant: str, agent: str, source_id: str) -> dict[str, Any]:
        """Return a saved text snapshot for staff review, including expired material."""
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT id,title,kind,uri,chars,created,review_by,customer_safe,pages "
                "FROM agent_sources WHERE tenant=? AND agent=? AND id=?",
                (tenant, agent, source_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("Source not found in this agent's knowledge.")
        source = dict(row)
        pages = json.loads(source.pop("pages"))
        return {
            "source": source,
            "pages": [
                {"page": index if source["kind"] == "pdf" else None, "text": text}
                for index, text in enumerate(pages, 1)
            ],
        }

    def add(
        self,
        tenant: str,
        agent: str,
        title: str,
        kind: str,
        pages: list[str],
        uri: str | None = None,
        review_by: date | None = None,
        customer_safe: bool = False,
    ) -> dict[str, Any]:
        title = title.strip()
        pages = [page.strip() for page in pages]
        if not title or len(title) > 200 or re.search(r"[\x00-\x1f\x7f]", title):
            raise DomainValidationError("Enter a source title between 1 and 200 characters.")
        if kind not in {"pdf", "website", "text", "markdown"}:
            raise DomainValidationError("Unsupported knowledge source type.")
        size = sum(map(len, pages))
        if not size or not any(pages):
            raise DomainValidationError("No readable text was found. Scanned PDFs need OCR first.")
        if size > MAX_SOURCE_CHARS or len(pages) > 100:
            raise DomainValidationError(
                "A source can contain up to 200,000 characters and 100 pages."
            )
        if review_by and review_by < date.today():
            raise DomainValidationError("Choose a review date that is today or later.")
        encoded = json.dumps(pages, ensure_ascii=False)
        source_id = hashlib.sha256(
            (kind + "\0" + (uri or "") + "\0" + encoded).encode()
        ).hexdigest()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM agent_sources WHERE tenant=? AND agent=? AND id=?",
                (tenant, agent, source_id),
            ).fetchone()
            if not existing:
                count, chars = db.execute(
                    "SELECT count(*),coalesce(sum(chars),0) FROM agent_sources WHERE tenant=? AND agent=?",
                    (tenant, agent),
                ).fetchone()
                if count >= MAX_AGENT_SOURCES or chars + size > MAX_AGENT_CHARS:
                    raise ConflictError(
                        "This agent's source capacity is full. Remove an older source first."
                    )
                db.execute(
                    "INSERT INTO agent_sources VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        tenant,
                        agent,
                        source_id,
                        title,
                        kind,
                        uri,
                        encoded,
                        size,
                        datetime.now(UTC).isoformat(),
                        review_by.isoformat() if review_by else None,
                        int(customer_safe),
                    ),
                )
            else:
                # Re-importing identical content must not silently remove its review deadline.
                db.execute(
                    "UPDATE agent_sources SET title=?,review_by=coalesce(?,review_by),customer_safe=? WHERE tenant=? AND agent=? AND id=?",
                    (
                        title,
                        review_by.isoformat() if review_by else None,
                        int(customer_safe),
                        tenant,
                        agent,
                        source_id,
                    ),
                )
            row = db.execute(
                "SELECT id,title,kind,uri,chars,created,review_by,customer_safe FROM agent_sources WHERE tenant=? AND agent=? AND id=?",
                (tenant, agent, source_id),
            ).fetchone()
            return dict(row)

    def remove(self, tenant: str, agent: str, source_id: str) -> None:
        with closing(self._connect()) as db, db:
            result = db.execute(
                "DELETE FROM agent_sources WHERE tenant=? AND agent=? AND id=?",
                (tenant, agent, source_id),
            )
            if result.rowcount != 1:
                raise NotFoundError("Source not found in this agent's knowledge.")

    def search(
        self, tenant: str, agent: str, question: str, *, customer: bool = False
    ) -> list[dict[str, Any]]:
        terms = question_terms(question)
        if not terms:
            return []
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT * FROM agent_sources WHERE tenant=? AND agent=? "
                "AND (review_by IS NULL OR review_by>=?) AND (?=0 OR customer_safe=1) ORDER BY id",
                (tenant, agent, date.today().isoformat(), int(customer)),
            ).fetchall()
        ranked: list[dict[str, Any]] = []
        for row in rows:
            for page_number, page in enumerate(json.loads(row["pages"]), 1):
                for index, passage in enumerate(chunk_text(page, chunk_size=700, overlap=80)):
                    matched = len(terms & passage_terms(passage))
                    score = matched / len(terms)
                    if matched < min(2, len(terms)) or score < 0.5:
                        continue
                    ranked.append(
                        {
                            "source_id": row["id"],
                            "title": row["title"],
                            "uri": row["uri"],
                            "page": page_number if row["kind"] == "pdf" else None,
                            "excerpt": passage,
                            "score": score,
                            "chunk": index,
                        }
                    )
        ranked.sort(
            key=lambda hit: (-hit["score"], hit["source_id"], hit["page"] or 0, hit["chunk"])
        )
        selected: list[dict[str, Any]] = []
        for hit in ranked:
            if any(s["source_id"] == hit["source_id"] for s in selected):
                continue
            selected.append(hit)
            if len(selected) == 3:
                break
        return selected

    def answer(self, tenant: str, agent: str, question: str) -> dict[str, Any]:
        sources = self.search(tenant, agent, question)
        return {
            "agent_id": agent,
            "answered": bool(sources),
            "supplied_sources_only": True,
            "method": "source-excerpts",
            "sent": False,
            "text": "\n\n".join(f"[{i + 1}] {s['excerpt']}" for i, s in enumerate(sources))
            or NO_ANSWER,
            "sources": [{**s, "label": str(i + 1)} for i, s in enumerate(sources)],
        }

    def tool_search(
        self, tenant: str, agent: str, question: str, customer: bool = True
    ) -> dict[str, Any]:
        sources = self.search(tenant, agent, question, customer=customer)
        return {
            "top_score": sources[0]["score"] if sources else 0.0,
            "has_stale": False,
            "citations": [
                {
                    "document_id": f"{tenant}:{s['source_id']}",
                    "title": s["title"],
                    "version": 1,
                    "chunk_id": f"{s['source_id']}:{s['page']}:{s['chunk']}",
                    "excerpt": s["excerpt"],
                }
                for s in sources
            ],
            "passages": [s["excerpt"] for s in sources],
        }

    def validate_message(
        self,
        tenant: str,
        agent: str | None,
        references: Any,
        body: str,
        subject: str | None = None,
    ) -> None:
        """Recheck the approved citation snapshot immediately before a provider call."""
        message = "Message sources changed or are unavailable. Prepare a new draft for review."
        if not agent or not isinstance(references, list) or not 1 <= len(references) <= 3:
            raise PolicyViolationError(message)
        try:
            citations = [Citation.model_validate(c) for c in references]
        except ValidationError:
            raise PolicyViolationError(message) from None
        seen: set[str] = set()
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            for citation in citations:
                prefix = tenant + ":"
                source_id = citation.document_id.removeprefix(prefix)
                if (
                    not citation.document_id.startswith(prefix)
                    or not re.fullmatch(r"[a-f0-9]{64}", source_id)
                    or source_id in seen
                    or citation.version != 1
                ):
                    raise PolicyViolationError(message)
                seen.add(source_id)
                row = db.execute(
                    "SELECT * FROM agent_sources WHERE tenant=? AND agent=? AND id=? "
                    "AND customer_safe=1 AND (review_by IS NULL OR review_by>=?)",
                    (tenant, agent, source_id, date.today().isoformat()),
                ).fetchone()
                if row is None or citation.title != row["title"]:
                    raise PolicyViolationError(message)
                matches = any(
                    citation.excerpt == passage
                    and citation.chunk_id
                    == f"{source_id}:{page if row['kind'] == 'pdf' else None}:{index}"
                    for page, text in enumerate(json.loads(row["pages"]), 1)
                    for index, passage in enumerate(chunk_text(text, chunk_size=700, overlap=80))
                )
                if not matches:
                    raise PolicyViolationError(message)
        if body != "\n\n".join(c.excerpt for c in citations):
            raise PolicyViolationError(message)
        if subject is not None and subject != citations[0].title:
            raise PolicyViolationError(message)
