
"""Add persistent lead consent and multiple deduplication keys.

Revision ID: 0002_lead_persistence
Revises: 0001_initial_schema
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_lead_persistence"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve communication consent and normalized phone region.
    op.add_column(
        "leads",
        sa.Column(
            "consent_marketing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "leads",
        sa.Column(
            "consent_whatsapp",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "leads",
        sa.Column("phone_region", sa.String(8), nullable=True),
    )

    # One lead can have multiple keys, such as email and phone.
    op.create_table(
        "lead_dedupe_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            sa.Uuid(),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "lead_id",
            "dedupe_key",
            name="uq_lead_dedupe_keys_org_lead_key",
        ),
    )

    op.create_index(
        "ix_lead_dedupe_keys_org_key",
        "lead_dedupe_keys",
        ["organization_id", "dedupe_key"],
    )

    op.create_index(
        "ix_lead_dedupe_keys_lead",
        "lead_dedupe_keys",
        ["lead_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_dedupe_keys_lead",
        table_name="lead_dedupe_keys",
    )

    op.drop_index(
        "ix_lead_dedupe_keys_org_key",
        table_name="lead_dedupe_keys",
    )

    op.drop_table("lead_dedupe_keys")

    op.drop_column("leads", "phone_region")
    op.drop_column("leads", "consent_whatsapp")
    op.drop_column("leads", "consent_marketing")
