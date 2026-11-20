
"""Add durable background-job recovery operations.

Revision ID: 0006_job_recovery_operations
Revises: 0005_job_outbox

Records the progress of Redis reservation reconciliation.

No raw job payloads or customer personal data are stored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_job_recovery_operations"
down_revision = "0005_job_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the recovery operations table."""

    op.create_table(
        "job_recovery_operations",

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
            "job_attempt",
            sa.Integer(),
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
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "error_code",
            sa.String(length=64),
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
            name="pk_job_recovery_operations",
        ),

        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=(
                "fk_job_recovery_operations_"
                "organization_id_organizations"
            ),
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["organization_id", "job_id"],
            [
                "background_jobs.organization_id",
                "background_jobs.job_id",
            ],
            name="fk_job_recovery_operations_background_job",
            ondelete="RESTRICT",
        ),

        sa.UniqueConstraint(
            "organization_id",
            "job_id",
            "job_attempt",
            name="uq_job_recovery_operations_org_job_attempt",
        ),

        sa.CheckConstraint(
            "job_attempt >= 1",
            name=sa.schema.conv(
                "ck_job_recovery_operations_positive_job_attempt"
            ),
        ),

        sa.CheckConstraint(
            "attempts >= 0",
            name=sa.schema.conv(
                "ck_job_recovery_operations_nonnegative_attempts"
            ),
        ),
    )

    op.create_index(
        "ix_job_recovery_operations_organization_id",
        "job_recovery_operations",
        ["organization_id"],
    )

    op.create_index(
        "ix_job_recovery_operations_status_retry",
        "job_recovery_operations",
        ["status", "next_attempt_at"],
    )

    op.create_index(
        "ix_job_recovery_operations_lease_expiry",
        "job_recovery_operations",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    """Remove the recovery operation table if downgraded."""

    op.drop_index(
        "ix_job_recovery_operations_lease_expiry",
        table_name="job_recovery_operations",
    )

    op.drop_index(
        "ix_job_recovery_operations_status_retry",
        table_name="job_recovery_operations",
    )

    op.drop_index(
        "ix_job_recovery_operations_organization_id",
        table_name="job_recovery_operations",
    )

    op.drop_table("job_recovery_operations")
