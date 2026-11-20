"""Durable tool execution ledger model.

Schema definition only. Not connected to ToolGateway or active workers.

An execution claim must not be automatically reassigned merely
because its owner disappears or a timeout has elapsed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import (
    Base,
    JsonType,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ToolExecutionLedger(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "tool_execution_ledger"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_tool_execution_ledger_org_key",
        ),
        Index(
            "ix_tool_execution_ledger_org_state",
            "organization_id",
            "state",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )

    tool_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    request_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="in_progress",
    )

    owner_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JsonType,
        nullable=True,
    )

    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
