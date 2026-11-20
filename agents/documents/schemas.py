from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from schemas.conversations.models import Citation


class DocumentAction(StrEnum):
    SUMMARIZE = "summarize"
    ANSWER = "answer"


class DocumentAgentInput(BaseModel):
    action: DocumentAction
    text: str | None = Field(default=None, max_length=200_000)
    query: str | None = Field(default=None, max_length=1000)
    audience: str = Field(default="customer", pattern="^(customer|staff)$")
    max_sentences: int = Field(default=3, ge=1, le=10)


class DocumentAgentOutput(BaseModel):
    summary: str | None = None
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0
    needs_human: bool = False
    notes: list[str] = Field(default_factory=list)
