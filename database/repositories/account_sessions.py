"""Opaque account sessions; requires trusted login and application composition.

issue_authenticated() is internal: call only after password or OIDC verification.
Supply a dedicated async session factory and a principal factory that converts
role strings to the application's Role enum. No engine or routes are installed.
"""

import base64
import hashlib
import re
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.security.account_contracts import PrincipalFactory, SessionFactory
from core.security.rbac import Principal


def table(table_name: str, **columns: sa.types.TypeEngine[Any]) -> sa.TableClause:
    return sa.table(table_name, *(sa.column(key, value) for key, value in columns.items()))


users = table(
    "users",
    id=sa.Uuid(),
    organization_id=sa.Uuid(),
    is_active=sa.Boolean(),
    approval_status=sa.String(16),
)
organizations = table("organizations", id=sa.Uuid(), is_active=sa.Boolean())
sessions = table(
    "account_sessions",
    id=sa.Uuid(),
    organization_id=sa.Uuid(),
    user_id=sa.Uuid(),
    token_digest=sa.String(64),
    auth_method=sa.String(16),
    issued_at=sa.DateTime(timezone=True),
    expires_at=sa.DateTime(timezone=True),
    revoked_at=sa.DateTime(timezone=True),
)
user_roles = table("user_roles", user_id=sa.Uuid(), role_id=sa.Uuid())
roles = table("roles", id=sa.Uuid(), name=sa.String(50))
audit = table(
    "audit_logs",
    id=sa.Uuid(),
    organization_id=sa.Uuid(),
    actor=sa.String(128),
    action=sa.String(64),
    resource_type=sa.String(64),
    resource_id=sa.String(128),
    outcome=sa.String(32),
    details=sa.JSON(),
)
KNOWN_ROLES = {
    "admin",
    "sales_manager",
    "sales_agent",
    "marketing",
    "analyst",
    "system",
    "viewer",
}


def token_digest(token: str) -> str:
    if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        raise HTTPException(401, "invalid session")
    decoded = base64.b64decode(token + "=", altchars=b"-_", validate=True)
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != 32 or canonical != token:
        raise HTTPException(401, "invalid session")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def user_state(user_id: UUID, organization_id: UUID) -> sa.Select[Any]:
    return (
        sa.select(users.c.id, users.c.organization_id, users.c.approval_status)
        .select_from(
            users.join(
                organizations,
                users.c.organization_id == organizations.c.id,
            )
        )
        .where(
            users.c.id == user_id,
            users.c.organization_id == organization_id,
            users.c.is_active.is_(True),
            organizations.c.is_active.is_(True),
            users.c.approval_status.in_(["pending", "approved"]),
        )
        .with_for_update(read=True)
    )


class AccountSessions:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        principal_factory: PrincipalFactory,
        ttl_seconds: int = 3600,
    ) -> None:
        if not callable(session_factory) or not callable(principal_factory):
            raise ValueError("trusted session and principal factories required")
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86400:
            raise ValueError("session lifetime must be 60 to 86400 seconds")
        self._factory = session_factory
        self._principal_factory = principal_factory
        self._ttl = ttl_seconds

    async def _audit(
        self, session: AsyncSession, row: Mapping[Any, Any], action: str, details: dict[str, Any]
    ) -> None:
        await session.execute(
            sa.insert(audit).values(
                id=uuid4(),
                organization_id=row["organization_id"],
                actor=str(row["user_id"]),
                action=action,
                resource_type="account_session",
                resource_id=str(row["id"]),
                outcome="success",
                details=details,
            )
        )

    async def issue_authenticated(
        self, user_id: UUID, organization_id: UUID, *, auth_method: str
    ) -> str:
        if (
            not isinstance(user_id, UUID)
            or not isinstance(organization_id, UUID)
            or user_id.int == 0
            or organization_id.int == 0
            or auth_method not in {"password", "google"}
        ):
            raise ValueError("valid authenticated identity and method required")
        token = secrets.token_urlsafe(32)
        digest = token_digest(token)
        now = datetime.now(UTC)
        row = {
            "id": uuid4(),
            "organization_id": organization_id,
            "user_id": user_id,
            "token_digest": digest,
            "auth_method": auth_method,
            "issued_at": now,
            "expires_at": now + timedelta(seconds=self._ttl),
            "revoked_at": None,
        }
        async with self._factory() as session, session.begin():
            state = (await session.execute(user_state(user_id, organization_id))).mappings().first()
            if state is None:
                raise HTTPException(401, "account unavailable")
            await session.execute(sa.insert(sessions).values(**row))
            await self._audit(
                session,
                row,
                "account.session.issued",
                {"auth_method": auth_method},
            )
        # Return only after transaction completion. Never log this token.
        return token

    async def verify(self, token: str) -> Principal:
        digest = token_digest(token)
        now = datetime.now(UTC)
        statement = (
            sa.select(
                sessions.c.user_id,
                sessions.c.organization_id,
                users.c.approval_status,
            )
            .select_from(
                sessions.join(
                    users,
                    sa.and_(
                        sessions.c.user_id == users.c.id,
                        sessions.c.organization_id == users.c.organization_id,
                    ),
                ).join(
                    organizations,
                    sessions.c.organization_id == organizations.c.id,
                )
            )
            .where(
                sessions.c.token_digest == digest,
                sessions.c.revoked_at.is_(None),
                sessions.c.issued_at <= now,
                sessions.c.expires_at > now,
                users.c.is_active.is_(True),
                organizations.c.is_active.is_(True),
                users.c.approval_status.in_(["pending", "approved"]),
            )
            .with_for_update(read=True)
        )
        async with self._factory() as session, session.begin():
            row = (await session.execute(statement)).mappings().first()
            if row is None:
                raise HTTPException(401, "invalid session")
            granted: frozenset[str] = frozenset()
            if row["approval_status"] == "approved":
                role_rows = (
                    (
                        await session.execute(
                            sa.select(roles.c.name)
                            .select_from(
                                user_roles.join(
                                    roles,
                                    user_roles.c.role_id == roles.c.id,
                                )
                            )
                            .where(user_roles.c.user_id == row["user_id"])
                        )
                    )
                    .mappings()
                    .all()
                )
                granted = frozenset(item["name"] for item in role_rows)
                if not granted.issubset(KNOWN_ROLES):
                    raise HTTPException(401, "account role unavailable")
            principal = self._principal_factory(
                subject=str(row["user_id"]),
                tenant_id=str(row["organization_id"]),
                roles=granted,
            )
        return principal

    async def revoke(self, token: str) -> bool:
        digest = token_digest(token)
        async with self._factory() as session, session.begin():
            row = (
                (
                    await session.execute(
                        sa.update(sessions)
                        .where(
                            sessions.c.token_digest == digest,
                            sessions.c.revoked_at.is_(None),
                        )
                        .values(revoked_at=sa.func.now())
                        .returning(
                            sessions.c.id,
                            sessions.c.organization_id,
                            sessions.c.user_id,
                        )
                    )
                )
                .mappings()
                .first()
            )
            if row is not None:
                await self._audit(session, row, "account.session.revoked", {})
        return row is not None
