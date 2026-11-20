from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationConnection(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("organization_id", "provider"),)

    provider: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16), default="mock")
    status: Mapped[str] = mapped_column(String(32), default="not_configured")
    # Non-secret settings only. Secrets live in env/secret manager; ``secret_ref``
    # names where to find them and is never the secret itself.
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String(200))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ExternalSyncRecord(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "external_sync_records"
    __table_args__ = (UniqueConstraint("connection_id", "entity_type", "external_id"),)

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("integration_connections.id", ondelete="CASCADE")
    )
    entity_type: Mapped[str] = mapped_column(String(32))
    local_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    direction: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    source_version: Mapped[str | None] = mapped_column(String(64))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
