
"""Add persistent background-job tracking.

Revision ID: 0004_background_job_tracking
Revises: 0003_unique_lead_dedupe_keys

Stores tenant-scoped job metadata, processing ownership,
lease expiry, retry scheduling, and final execution status.

No raw job payloads or customer personal data are stored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_background_job_tracking"
down_revision = "0003_unique_lead_dedupe_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the background_jobs table and indexes."""

    op.create_table(
        "background_jobs",

        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.Column(
            "organization_id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.Column(
            "job_id",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "job_type",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),

        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),

        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),

        sa.Column(
            "worker_id",
            sa.String(length=128),
            nullable=True,
        ),

        sa.Column(
            "lease_token",
            sa.String(length=64),
            nullable=True,
        ),

        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "correlation_id",
            sa.String(length=64),
            nullable=True,
        ),

        sa.Column(
            "error_code",
            sa.String(length=64),
            nullable=True,
        ),

        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_background_jobs",
        ),

        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_background_jobs_organization_id_organizations",
            ondelete="RESTRICT",
        ),

        sa.UniqueConstraint(
            "organization_id",
            "job_id",
            name="uq_background_jobs_org_job_id",
        ),

        # conv() prevents the existing SQLAlchemy naming
        # convention from applying the prefix a second time.
        sa.CheckConstraint(
            "attempts >= 0",
            name=sa.schema.conv(
                "ck_background_jobs_nonnegative_attempts"
            ),
        ),

        sa.CheckConstraint(
            "max_attempts >= 1",
            name=sa.schema.conv(
                "ck_background_jobs_positive_max_attempts"
            ),
        ),
    )

    # Tenant lookup index.
    op.create_index(
        "ix_background_jobs_organization_id",
        "background_jobs",
        ["organization_id"],
    )

    # List a tenant's jobs by execution status.
    op.create_index(
        "ix_background_jobs_org_status",
        "background_jobs",
        ["organization_id", "status"],
    )

    # Find expired processing leases for recovery.
    op.create_index(
        "ix_background_jobs_lease_expiry",
        "background_jobs",
        ["status", "lease_expires_at"],
    )

    # Find retryable jobs when their scheduled delay expires.
    op.create_index(
        "ix_background_jobs_next_retry",
        "background_jobs",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    """Remove only the background-job tracking table."""

    op.drop_index(
        "ix_background_jobs_next_retry",
        table_name="background_jobs",
    )

    op.drop_index(
        "ix_background_jobs_lease_expiry",
        table_name="background_jobs",
    )

    op.drop_index(
        "ix_background_jobs_org_status",
        table_name="background_jobs",
    )

    op.drop_index(
        "ix_background_jobs_organization_id",
        table_name="background_jobs",
    )

    op.drop_table("background_jobs")
