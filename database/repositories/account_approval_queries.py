"""Account approval SQL builders; no connection or session creation.

Callers must supply identifiers from verified authentication and trusted owner
configuration, never owner/actor identifiers supplied by a public request.

Execution requires a transaction, decision-result checking and an audit write.
These statements do not authenticate a caller or provision the initial owner.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

_users = sa.table(
    "users",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("email", sa.String(254)),
    sa.column("full_name", sa.String(200)),
    sa.column("is_active", sa.Boolean()),
    sa.column("approval_status", sa.String(16)),
    sa.column("approval_decided_by", sa.Uuid()),
    sa.column("approval_decided_at", sa.DateTime(timezone=True)),
)
_organizations = sa.table(
    "organizations",
    sa.column("id", sa.Uuid()),
    sa.column("is_active", sa.Boolean()),
)


def _uuid(value: uuid.UUID) -> uuid.UUID:
    if not isinstance(value, uuid.UUID):
        raise ValueError("UUID identifier required")
    return value


def _organization_active(organization_id: uuid.UUID):
    return (
        sa.select(sa.literal(1))
        .select_from(_organizations)
        .where(
            _organizations.c.id == organization_id,
            _organizations.c.is_active.is_(True),
        )
        .exists()
    )


def _owner_allowed(
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    configured_owner_user_id: uuid.UUID,
):
    _uuid(organization_id)
    _uuid(actor_user_id)
    _uuid(configured_owner_user_id)
    if actor_user_id != configured_owner_user_id:
        raise PermissionError("owner identity required")
    owner = _users.alias("approval_owner")
    return (
        sa.select(sa.literal(1))
        .select_from(owner)
        .where(
            owner.c.id == actor_user_id,
            owner.c.organization_id == organization_id,
            owner.c.is_active.is_(True),
            owner.c.approval_status == "approved",
        )
        .exists()
    )


def build_pending_accounts(
    organization_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID,
    configured_owner_user_id: uuid.UUID,
):
    owner_allowed = _owner_allowed(organization_id, actor_user_id, configured_owner_user_id)
    return (
        sa.select(
            _users.c.id,
            _users.c.organization_id,
            _users.c.email,
            _users.c.full_name,
            _users.c.approval_status,
        )
        .where(
            _users.c.organization_id == organization_id,
            _users.c.approval_status == "pending",
            _users.c.is_active.is_(True),
            _organization_active(organization_id),
            owner_allowed,
        )
        .order_by(_users.c.id)
    )


def build_account_decision(
    target_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID,
    configured_owner_user_id: uuid.UUID,
    approve: bool,
):
    _uuid(target_user_id)
    if type(approve) is not bool:
        raise ValueError("approve must be boolean")
    owner_allowed = _owner_allowed(organization_id, actor_user_id, configured_owner_user_id)
    if target_user_id == actor_user_id:
        raise PermissionError("self-approval is prohibited")
    return (
        sa.update(_users)
        .where(
            _users.c.id == target_user_id,
            _users.c.organization_id == organization_id,
            _users.c.approval_status == "pending",
            _users.c.is_active.is_(True),
            _organization_active(organization_id),
            owner_allowed,
        )
        .values(
            approval_status="approved" if approve else "rejected",
            approval_decided_by=actor_user_id,
            approval_decided_at=sa.func.now(),
        )
        .returning(
            _users.c.id,
            _users.c.organization_id,
            _users.c.approval_status,
            _users.c.approval_decided_by,
            _users.c.approval_decided_at,
        )
    )


def build_own_dashboard_access(
    authenticated_user_id: uuid.UUID,
    authenticated_organization_id: uuid.UUID,
):
    _uuid(authenticated_user_id)
    _uuid(authenticated_organization_id)
    return sa.select(
        _users.c.id,
        _users.c.organization_id,
        _users.c.full_name,
        _users.c.approval_status,
    ).where(
        _users.c.id == authenticated_user_id,
        _users.c.organization_id == authenticated_organization_id,
        _users.c.approval_status == "approved",
        _users.c.is_active.is_(True),
        _organization_active(authenticated_organization_id),
    )
