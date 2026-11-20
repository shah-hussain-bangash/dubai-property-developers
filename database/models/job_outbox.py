
"""Transactional outbox model for reliable background-job publishing.

Stores encrypted job-envelope data awaiting publication to Redis.

Plaintext customer data must never be written to this table.
Application encryption and dispatcher logic are implemented
in a separate development phase.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
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


class JobOutbox(
    UUIDPrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
    Base,
):
    """Durable, encrypted publication record for a background job."""

    __tablename__ = "job_outbox"

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            [
                "background_jobs.organization_id",
                "background_jobs.job_id",
            ],
            name="fk_job_outbox_background_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "job_id",
            name="uq_job_outbox_org_job_id",
        ),
        Index(
            "ix_job_outbox_status_retry",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_job_outbox_lease_expiry",
            "status",
            "lease_expires_at",
        ),
        CheckConstraint(
            "publish_attempts >= 0",
            name="nonnegative_publish_attempts",
        ),
    )

    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    payload_ciphertext: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )

    encryption_key_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    publish_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
