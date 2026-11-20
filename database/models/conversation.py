from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "external_thread_id"),
        Index("ix_conversations_org_status", "organization_id", "status"),
    )

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="open")
    external_thread_id: Mapped[str | None] = mapped_column(String(128))
    # Drives the WhatsApp 24-hour customer-service window check.
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    state: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Message(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "external_message_id"),
        Index("ix_messages_conversation_sent", "conversation_id", "sent_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE")
    )
    direction: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(32))
    sender_type: Mapped[str] = mapped_column(String(32))
    sender_ref: Mapped[str | None] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    external_message_id: Mapped[str | None] = mapped_column(String(128))
    delivery_status: Mapped[str] = mapped_column(String(32), default="draft")
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id", ondelete="SET NULL")
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
