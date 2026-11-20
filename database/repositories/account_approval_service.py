"""Transactional account service, awaiting application integration.

Creates no engine and imports no project modules. A trusted composition layer
must supply a dedicated async session factory, verified actors, and owner UUIDs.
Requires the reviewed account-approval schema to be applied before live use.
"""
from types import MappingProxyType
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException

users = sa.table(
    "users",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("full_name", sa.String(200)),
    sa.column("is_active", sa.Boolean()),
    sa.column("approval_status", sa.String(16)),
    sa.column("approval_decided_by", sa.Uuid()),
    sa.column("approval_decided_at", sa.DateTime(timezone=True)),
)
organizations = sa.table(
    "organizations",
    sa.column("id", sa.Uuid()),
    sa.column("is_active", sa.Boolean()),
)
audit_logs = sa.table(
    "audit_logs",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("actor", sa.String(128)),
    sa.column("action", sa.String(64)),
    sa.column("resource_type", sa.String(64)),
    sa.column("resource_id", sa.String(128)),
    sa.column("outcome", sa.String(32)),
    sa.column("details", sa.JSON()),
)

def _uuid(value):
    if not isinstance(value, UUID):
        raise ValueError("UUID identifier required")
    return value

def _view(row):
    return {
        "account_id": row["id"],
        "organization_id": row["organization_id"],
        "full_name": row["full_name"],
        "approval_status": row["approval_status"],
    }

class TransactionalAccountService:
    def __init__(self, session_factory, *, owners):
        if not callable(session_factory):
            raise ValueError("dedicated session factory required")
        copied = {}
        for organization_id, owner_id in owners.items():
            copied[_uuid(organization_id)] = _uuid(owner_id)
        self._factory = session_factory
        self._owners = MappingProxyType(copied)

    def owner_subject(self, organization_id):
        return self._owners.get(_uuid(organization_id))

    def _actor(self, actor):
        return _uuid(actor.user_id), _uuid(actor.organization_id)

    async def _lock_organization(self, session, organization_id):
        statement = (
            sa.select(organizations.c.id)
            .where(
                organizations.c.id == organization_id,
                organizations.c.is_active.is_(True),
            )
            .with_for_update(read=True)
        )
        row = (await session.execute(statement)).mappings().first()
        if row is None:
            raise HTTPException(403, "account access denied")

    async def _lock_owner(self, session, user_id, organization_id):
        if self.owner_subject(organization_id) != user_id:
            raise HTTPException(403, "owner approval required")
        statement = (
            sa.select(users.c.id)
            .where(
                users.c.id == user_id,
                users.c.organization_id == organization_id,
                users.c.is_active.is_(True),
                users.c.approval_status == "approved",
            )
            .with_for_update(read=True)
        )
        row = (await session.execute(statement)).mappings().first()
        if row is None:
            raise HTTPException(403, "owner approval required")

    async def list_pending(self, actor, *, limit):
        user_id, organization_id = self._actor(actor)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        if self.owner_subject(organization_id) != user_id:
            raise HTTPException(403, "owner approval required")
        async with self._factory() as session:
            async with session.begin():
                await self._lock_organization(session, organization_id)
                await self._lock_owner(session, user_id, organization_id)
                statement = (
                    sa.select(
                        users.c.id, users.c.organization_id,
                        users.c.full_name, users.c.approval_status,
                    )
                    .where(
                        users.c.organization_id == organization_id,
                        users.c.is_active.is_(True),
                        users.c.approval_status == "pending",
                    )
                    .order_by(users.c.id)
                    .limit(limit)
                )
                rows = (await session.execute(statement)).mappings().all()
                result = [_view(row) for row in rows]
        return result

    async def decide(self, actor, target_id, *, approve):
        user_id, organization_id = self._actor(actor)
        _uuid(target_id)
        if type(approve) is not bool:
            raise ValueError("approve must be boolean")
        if self.owner_subject(organization_id) != user_id:
            raise HTTPException(403, "owner approval required")
        if target_id == user_id:
            raise HTTPException(403, "self-approval prohibited")
        status = "approved" if approve else "rejected"
        async with self._factory() as session:
            async with session.begin():
                await self._lock_organization(session, organization_id)
                await self._lock_owner(session, user_id, organization_id)
                statement = (
                    sa.update(users)
                    .where(
                        users.c.id == target_id,
                        users.c.organization_id == organization_id,
                        users.c.is_active.is_(True),
                        users.c.approval_status == "pending",
                    )
                    .values(
                        approval_status=status,
                        approval_decided_by=user_id,
                        approval_decided_at=sa.func.now(),
                    )
                    .returning(
                        users.c.id, users.c.organization_id,
                        users.c.full_name, users.c.approval_status,
                    )
                )
                row = (await session.execute(statement)).mappings().first()
                if row is None:
                    raise HTTPException(409, "account is not eligible for a decision")
                await session.execute(
                    sa.insert(audit_logs).values(
                        id=uuid4(),
                        organization_id=organization_id,
                        actor=str(user_id),
                        action="account.approval.decided",
                        resource_type="user",
                        resource_id=str(target_id),
                        outcome=status,
                        details={"previous_status": "pending", "status": status},
                    )
                )
                result = _view(row)
        return result

    async def get_self(self, actor):
        user_id, organization_id = self._actor(actor)
        async with self._factory() as session:
            async with session.begin():
                await self._lock_organization(session, organization_id)
                statement = (
                    sa.select(
                        users.c.id, users.c.organization_id,
                        users.c.full_name, users.c.approval_status,
                    )
                    .where(
                        users.c.id == user_id,
                        users.c.organization_id == organization_id,
                        users.c.is_active.is_(True),
                    )
                    .with_for_update(read=True)
                )
                row = (await session.execute(statement)).mappings().first()
                if row is None:
                    raise HTTPException(403, "account access denied")
                result = _view(row)
        return result

    async def require_dashboard_access(self, actor):
        result = await self.get_self(actor)
        if result["approval_status"] != "approved":
            raise HTTPException(403, "approved account required")
        return result
