"""Proposed authentication storage; offline review only.

Requires the separately staged user approval migration.
Creates no owner, users, approvals, identities, or sessions.
Application code must generate opaque session tokens and store only their hash.
Google identities must not be linked to existing accounts by email alone.
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_account_auth_storage"
down_revision = "0009_user_account_approval"
branch_labels = None
depends_on = None

def upgrade():
    # Composite keys enforce that each reference belongs to the same tenant.
    op.create_unique_constraint(
        op.f("uq_users_organization_id_id"),
        "users", ["organization_id", "id"],
    )
    op.create_table(
        "user_external_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_user_external_identities"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name=op.f("fk_external_identity_tenant_user"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "issuer", "subject",
            name=op.f("uq_external_identity_tenant_subject"),
        ),
        sa.CheckConstraint(
            "issuer = 'https://accounts.google.com'",
            name=op.f("ck_external_identity_google_issuer"),
        ),
        sa.CheckConstraint(
            "length(btrim(subject)) > 0",
            name=op.f("ck_external_identity_nonempty_subject"),
        ),
    )
    op.create_index(
        op.f("ix_external_identity_tenant_user"),
        "user_external_identities", ["organization_id", "user_id"],
    )
    op.create_table(
        "account_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("auth_method", sa.String(16), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_sessions")),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name=op.f("fk_account_session_tenant_user"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "token_digest", name=op.f("uq_account_session_token_digest"),
        ),
        sa.CheckConstraint(
            "token_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_account_session_digest_format"),
        ),
        sa.CheckConstraint(
            "auth_method IN ('password', 'google')",
            name=op.f("ck_account_session_auth_method"),
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name=op.f("ck_account_session_expiry"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name=op.f("ck_account_session_revocation"),
        ),
    )
    op.create_index(
        op.f("ix_account_session_tenant_user"),
        "account_sessions", ["organization_id", "user_id"],
    )
    op.create_index(
        op.f("ix_account_session_expiry"),
        "account_sessions", ["expires_at"],
    )

def downgrade():
    # Applying downgrade would delete identity links and sessions.
    op.drop_index(
        op.f("ix_account_session_expiry"), table_name="account_sessions",
    )
    op.drop_index(
        op.f("ix_account_session_tenant_user"), table_name="account_sessions",
    )
    op.drop_table("account_sessions")
    op.drop_index(
        op.f("ix_external_identity_tenant_user"),
        table_name="user_external_identities",
    )
    op.drop_table("user_external_identities")
    op.drop_constraint(
        op.f("uq_users_organization_id_id"), "users", type_="unique",
    )
