
"""Persistent background-job tracking model.

Tracks job ownership, lease expiry, retries, and final outcomes.

This table stores job metadata only.
Do not store raw customer lead payloads, emails, phone numbers,
WhatsApp messages, or other sensitive job content here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class BackgroundJob(
    UUIDPrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
    Base,
):
    """Durable metadata for a Redis background job."""

    __tablename__ = "background_jobs"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "job_id",
            name="uq_background_jobs_org_job_id",
        ),
        Index(
            "ix_background_jobs_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_background_jobs_lease_expiry",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_background_jobs_next_retry",
            "status",
            "next_retry_at",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="nonnegative_attempts",
        ),
        CheckConstraint(
            "max_attempts >= 1",
            name="positive_max_attempts",
        ),
    )

    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    job_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )

    worker_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    lease_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    correlation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
