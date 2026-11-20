
"""Enforce tenant-scoped uniqueness of lead deduplication keys.

Revision ID: 0003_unique_lead_dedupe_keys
Revises: 0002_lead_persistence
"""

from __future__ import annotations

from alembic import op

revision = "0003_unique_lead_dedupe_keys"
down_revision = "0002_lead_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_lead_dedupe_keys_org_key",
        "lead_dedupe_keys",
        ["organization_id", "dedupe_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_lead_dedupe_keys_org_key",
        "lead_dedupe_keys",
        type_="unique",
    )
