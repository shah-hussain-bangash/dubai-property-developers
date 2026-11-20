
"""Add transactional background-job publication outbox.

Revision ID: 0005_job_outbox
Revises: 0004_background_job_tracking

Creates a durable outbox table for encrypted job envelopes.
The outbox supports publication attempts, dispatcher leases,
retry scheduling, and publication status tracking.

Encryption is not performed by this migration. Application code
must encrypt and authenticate all envelope data before insertion.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_job_outbox"
down_revision = "0004_background_job_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the transactional job outbox."""

    op.create_table(
        "job_outbox",

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
            "payload_ciphertext",
            sa.LargeBinary(),
            nullable=False,
        ),

        sa.Column(
            "encryption_key_id",
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
            "publish_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),

        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
            "published_at",
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
            name="pk_job_outbox",
        ),

        # Standard tenant foreign key from TenantMixin.
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_job_outbox_organization_id_organizations",
            ondelete="RESTRICT",
        ),

        # Composite foreign key guarantees that the outbox
        # points to a job belonging to the SAME organization.
        sa.ForeignKeyConstraint(
            ["organization_id", "job_id"],
            [
                "background_jobs.organization_id",
                "background_jobs.job_id",
            ],
            name="fk_job_outbox_background_job",
            ondelete="RESTRICT",
        ),

        # One publication record per tenant/job combination.
        sa.UniqueConstraint(
            "organization_id",
            "job_id",
            name="uq_job_outbox_org_job_id",
        ),

        # Prevent invalid negative publication counters.
        sa.CheckConstraint(
            "publish_attempts >= 0",
            name=sa.schema.conv(
                "ck_job_outbox_nonnegative_publish_attempts"
            ),
        ),
    )

    # Tenant-scoped lookup.
    op.create_index(
        "ix_job_outbox_organization_id",
        "job_outbox",
        ["organization_id"],
    )

    # Dispatcher query: pending publication or scheduled retry.
    op.create_index(
        "ix_job_outbox_status_retry",
        "job_outbox",
        ["status", "next_attempt_at"],
    )

    # Dispatcher recovery query: abandoned publication leases.
    op.create_index(
        "ix_job_outbox_lease_expiry",
        "job_outbox",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    """Remove the outbox only if explicitly downgraded."""

    op.drop_index(
        "ix_job_outbox_lease_expiry",
        table_name="job_outbox",
    )

    op.drop_index(
        "ix_job_outbox_status_retry",
        table_name="job_outbox",
    )

    op.drop_index(
        "ix_job_outbox_organization_id",
        table_name="job_outbox",
    )

    op.drop_table("job_outbox")
