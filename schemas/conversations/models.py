from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Channel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    WEB_CHAT = "web_chat"
    PHONE = "phone"
    SMS = "sms"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CustomerIntent(StrEnum):
    PROPERTY_ENQUIRY = "property_enquiry"
    PRICING = "pricing"
    PAYMENT_PLAN = "payment_plan"
    SCHEDULE_VIEWING = "schedule_viewing"
    CALLBACK_REQUEST = "callback_request"
    COMPLAINT = "complaint"
    UNSUBSCRIBE = "unsubscribe"
    GENERAL = "general"
    UNKNOWN = "unknown"


class ConversationMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    conversation_id: str
    channel: Channel
    direction: MessageDirection
    sender: str
    text: str = Field(max_length=4096)
    language: str | None = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Citation(BaseModel):
    document_id: str
    title: str
    version: int
    chunk_id: str
    excerpt: str


class DraftReply(BaseModel):
    text: str
    channel: Channel
    language: str = "en"
    requires_approval: bool = True
    escalate: bool = False
    escalation_reason: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    is_template: bool = False
