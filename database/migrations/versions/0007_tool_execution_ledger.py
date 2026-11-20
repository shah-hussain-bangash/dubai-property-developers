"""Create the durable tool execution ledger.

Revision ID: 0007_tool_execution_ledger
Revises: 0006_job_recovery_operations

Schema-only migration. Does not enable execution claims,
change workers, send messages, or activate recovery.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from database.base import JsonType


revision = "0007_tool_execution_ledger"
down_revision = "0006_job_recovery_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_execution_ledger",

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
            "idempotency_key",
            sa.String(length=256),
            nullable=False,
        ),

        sa.Column(
            "tool_name",
            sa.String(length=128),
            nullable=False,
        ),

        sa.Column(
            "state",
            sa.String(length=32),
            nullable=False,
        ),

        sa.Column(
            "owner_token",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "result_json",
            JsonType,
            nullable=True,
        ),

        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "completed_at",
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
            name="pk_tool_execution_ledger",
        ),

        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_tool_execution_ledger_organization_id_organizations",
            ondelete="RESTRICT",
        ),

        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_tool_execution_ledger_org_key",
        ),
    )

    op.create_index(
        "ix_tool_execution_ledger_organization_id",
        "tool_execution_ledger",
        ["organization_id"],
    )

    op.create_index(
        "ix_tool_execution_ledger_org_state",
        "tool_execution_ledger",
        ["organization_id", "state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_execution_ledger_org_state",
        table_name="tool_execution_ledger",
    )

    op.drop_index(
        "ix_tool_execution_ledger_organization_id",
        table_name="tool_execution_ledger",
    )

    op.drop_table("tool_execution_ledger")
