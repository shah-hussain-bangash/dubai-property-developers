
"""Durable metadata for background-job recovery operations.

Each record represents recovery of a specific execution attempt.

This table must not store raw Redis messages, lead information,
customer details, or other job payload content.

A recovery operation records progress, but does not itself make
PostgreSQL and Redis updates atomic.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
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


class JobRecoveryOperation(
    UUIDPrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
    Base,
):
    """Track one recovery operation for one job execution attempt."""

    __tablename__ = "job_recovery_operations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            [
                "background_jobs.organization_id",
                "background_jobs.job_id",
            ],
            name="fk_job_recovery_operations_background_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "job_id",
            "job_attempt",
            name="uq_job_recovery_operations_org_job_attempt",
        ),
        Index(
            "ix_job_recovery_operations_status_retry",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_job_recovery_operations_lease_expiry",
            "status",
            "lease_expires_at",
        ),
        CheckConstraint(
            "job_attempt >= 1",
            name="positive_job_attempt",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="nonnegative_attempts",
        ),
    )

    # The inherited UUID primary key, `id`, is the operation ID.

    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # PostgreSQL background_jobs.attempts at the time recovery
    # begins. Each execution attempt has one recovery operation.
    job_attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    # Number of reconciliation attempts, not handler attempts.
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
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

    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
