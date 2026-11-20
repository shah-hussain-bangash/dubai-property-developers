"""Add durable request fingerprint to execution ledger.

Existing rows remain nullable for migration compatibility.
Claims without fingerprints must be treated as unverified
and must not be replayed automatically.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008_tool_request_fingerprint"
down_revision = "0007_tool_execution_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_execution_ledger",
        sa.Column(
            "request_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "tool_execution_ledger",
        "request_fingerprint",
    )
