from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from schemas.conversations.models import Citation, CustomerIntent


class ReplyMode(StrEnum):
    FREE_TEXT = "free_text"
    TEMPLATE_REQUIRED = "template_required"
    NO_REPLY = "no_reply"


class WhatsAppAgentInput(BaseModel):
    conversation_id: str
    from_e164: str
    text: str = Field(max_length=4096)
    received_at: datetime
    consent_whatsapp: bool
    customer_first_name: str | None = None
    draft_reply: str | None = None  # optional draft from the sales agent
    send_reply: bool = False


class WhatsAppAgentOutput(BaseModel):
    intent: CustomerIntent
    reply_mode: ReplyMode
    reply_text: str | None = None
    template_name: str | None = None
    send_status: str | None = None
    approval_id: str | None = None
    escalate: bool = False
    notes: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
