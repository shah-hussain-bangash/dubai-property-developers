from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.conversations.models import ConversationMessage, CustomerIntent, DraftReply


class SalesConversationInput(BaseModel):
    message: ConversationMessage
    customer_first_name: str | None = Field(default=None, max_length=60)


class SalesConversationOutput(BaseModel):
    intent: CustomerIntent
    language: str
    draft: DraftReply
    injection_signals: list[str] = Field(default_factory=list)
    retrieval_top_score: float = 0.0
