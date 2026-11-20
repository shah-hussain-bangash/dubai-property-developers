"""Knowledge document and chunk models (versioned, permission-tagged)."""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AccessLevel(StrEnum):
    PUBLIC = "public"  # may be quoted to customers
    INTERNAL = "internal"  # staff and agents only
    RESTRICTED = "restricted"  # only principals holding one of allowed_roles


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class SourceDocument(BaseModel):
    tenant_id: str
    document_key: str  # stable identity across versions
    version: int = Field(default=1, ge=1)
    title: str
    text: str
    mime_type: str = "text/plain"
    source_uri: str | None = None
    access_level: AccessLevel = AccessLevel.INTERNAL
    allowed_roles: list[str] = Field(default_factory=list)
    effective_date: date | None = None
    review_by: date | None = None  # after this date content is treated as stale
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def document_id(self) -> str:
        return f"{self.tenant_id}:{self.document_key}:v{self.version}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


class Chunk(BaseModel):
    chunk_id: str
    tenant_id: str
    document_id: str
    document_key: str
    version: int
    title: str
    chunk_index: int
    content: str
    access_level: AccessLevel
    allowed_roles: list[str] = Field(default_factory=list)
    status: DocumentStatus = DocumentStatus.ACTIVE
    review_by: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float
    stale: bool = False
