"""Proposed user approval fields; staged for review only.

Existing rows retain NULL status and require explicit review.
Only inserts after the migration receive the pending server default.
No owner is created or approved automatically.
Do not run before migration authorization and owner-provisioning review.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_user_account_approval"
down_revision = "0008_tool_request_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add without a default first, preserving NULL for existing accounts.
    op.add_column("users", sa.Column(
        "approval_status", sa.String(length=16), nullable=True
    ))
    op.add_column("users", sa.Column(
        "approval_decided_by", sa.Uuid(), nullable=True
    ))
    op.add_column("users", sa.Column(
        "approval_decided_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.create_foreign_key(
        op.f("fk_users_approval_decided_by_users"),
        "users", "users", ["approval_decided_by"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_users_account_approval_status"), "users",
        "approval_status IS NULL OR approval_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_check_constraint(
        op.f("ck_users_account_approval_decision"), "users",
        "((approval_status IS NULL OR approval_status = 'pending') AND approval_decided_by IS NULL AND approval_decided_at IS NULL) OR (approval_status IS NOT NULL AND approval_status IN ('approved', 'rejected') AND approval_decided_by IS NOT NULL AND approval_decided_at IS NOT NULL)",
    )
    op.alter_column(
        "users", "approval_status",
        existing_type=sa.String(length=16),
        server_default=sa.text("'pending'"),
    )


def downgrade() -> None:
    # Removing these fields discards approval decisions.
    op.drop_constraint(
        op.f("ck_users_account_approval_decision"), "users", type_="check"
    )
    op.drop_constraint(
        op.f("ck_users_account_approval_status"), "users", type_="check"
    )
    op.drop_constraint(
        op.f("fk_users_approval_decided_by_users"), "users", type_="foreignkey"
    )
    op.drop_column("users", "approval_decided_at")
    op.drop_column("users", "approval_decided_by")
    op.drop_column("users", "approval_status")
