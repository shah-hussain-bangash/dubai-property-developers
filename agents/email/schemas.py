from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field

from schemas.conversations.models import Citation


class EmailMode(StrEnum):
    DRAFT = "draft"  # render only
    SEND = "send"  # render, then request send (approval-gated)
    CLASSIFY = "classify"  # classify an inbound reply


class InboundClassification(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    UNSUBSCRIBE = "unsubscribe"
    OUT_OF_OFFICE = "out_of_office"
    QUESTION = "question"
    OTHER = "other"


class EmailAgentInput(BaseModel):
    mode: EmailMode = EmailMode.DRAFT
    template: str | None = None
    recipient_email: EmailStr | None = None
    first_name: str = Field(default="", max_length=60)
    advisor_name: str = Field(default="Your advisor", max_length=80)
    is_marketing: bool = False
    consent_marketing: bool = False
    inbound_text: str | None = Field(default=None, max_length=10_000)
    knowledge_query: str | None = Field(default=None, min_length=3, max_length=1000)


class EmailAgentOutput(BaseModel):
    subject: str | None = None
    body: str | None = None
    send_status: str | None = None  # "pending_approval" | "executed" | "replayed"
    approval_id: str | None = None
    classification: InboundClassification | None = None
    citations: list[Citation] = Field(default_factory=list)
    needs_human: bool = False
    notes: list[str] = Field(default_factory=list)
