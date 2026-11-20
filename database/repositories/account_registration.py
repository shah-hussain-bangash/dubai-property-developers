"""Pending account registration; awaiting trusted authentication composition.

The organization UUID must come from trusted server-side organization routing.
google_account() must receive only GoogleOIDC.complete() output, never browser
claims. Password registration requires a separately reviewed password hasher.
No login sessions, roles, owner accounts, or approvals are created here.
"""

import asyncio
from collections.abc import Mapping
from uuid import UUID, uuid4

import sqlalchemy as sa
from email_validator import validate_email
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


def table(table_name, **columns):
    return sa.table(
        table_name,
        *(sa.column(key, value) for key, value in columns.items()),
    )


users = table(
    "users",
    id=sa.Uuid(),
    organization_id=sa.Uuid(),
    email=sa.String(254),
    full_name=sa.String(200),
    password_hash=sa.String(255),
    is_active=sa.Boolean(),
    approval_status=sa.String(16),
    approval_decided_by=sa.Uuid(),
    approval_decided_at=sa.DateTime(timezone=True),
)
organizations = table("organizations", id=sa.Uuid(), is_active=sa.Boolean())
identities = table(
    "user_external_identities",
    id=sa.Uuid(),
    organization_id=sa.Uuid(),
    user_id=sa.Uuid(),
    issuer=sa.String(255),
    subject=sa.String(255),
)
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
GOOGLE_ISSUER = "https://accounts.google.com"


def account_view(row):
    return {
        "account_id": row["id"],
        "organization_id": row["organization_id"],
        "full_name": row["full_name"],
        "approval_status": row["approval_status"],
    }


class PendingAccountRegistration:
    def __init__(self, session_factory, *, password_hasher):
        if not callable(session_factory) or not callable(password_hasher):
            raise ValueError("trusted session factory and password hasher required")
        self._factory = session_factory
        self._password_hasher = password_hasher

    def _validate(self, organization_id, email, full_name):
        if not isinstance(organization_id, UUID) or organization_id.int == 0:
            raise ValueError("trusted organization UUID required")
        if not isinstance(email, str) or len(email) > 254:
            raise ValueError("valid email required")
        normalized = validate_email(email, check_deliverability=False).normalized
        if len(normalized) > 254:
            raise ValueError("email exceeds storage limit")
        if not isinstance(full_name, str) or not full_name.strip() or len(full_name.strip()) > 200:
            raise ValueError("full name must contain 1 to 200 characters")
        return normalized, full_name.strip()

    async def _lock_organization(self, session, organization_id):
        # Serialize registrations within an organization to avoid competing
        # identity/email checks among callers of this service.
        row = (
            (
                await session.execute(
                    sa.select(organizations.c.id)
                    .where(
                        organizations.c.id == organization_id,
                        organizations.c.is_active.is_(True),
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(403, "registration unavailable")

    async def _create(self, session, organization_id, email, name, digest):
        existing = (
            (
                await session.execute(
                    sa.select(users.c.id).where(
                        users.c.organization_id == organization_id,
                        users.c.email == email,
                    )
                )
            )
            .mappings()
            .first()
        )
        if existing is not None:
            raise HTTPException(409, "use an existing sign-in method or explicit account linking")
        row = {
            "id": uuid4(),
            "organization_id": organization_id,
            "email": email,
            "full_name": name,
            "password_hash": digest,
            "is_active": True,
            "approval_status": "pending",
            "approval_decided_by": None,
            "approval_decided_at": None,
        }
        await session.execute(sa.insert(users).values(**row))
        return row

    async def _audit_creation(self, session, row, method):
        await session.execute(
            sa.insert(audit).values(
                id=uuid4(),
                organization_id=row["organization_id"],
                actor=str(row["id"]),
                action="account.registered",
                resource_type="user",
                resource_id=str(row["id"]),
                outcome="pending",
                details={"auth_method": method},
            )
        )

    async def register_password(self, organization_id, *, email, full_name, password):
        normalized, name = self._validate(organization_id, email, full_name)
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            raise ValueError("password must contain 12 to 1024 characters")
        try:
            if len(password.encode("utf-8")) > 4096:
                raise ValueError("password exceeds byte limit")
        except UnicodeError:
            raise ValueError("password cannot be encoded") from None
        # Composition must supply a reviewed hasher; held modules are not imported.
        digest = await asyncio.to_thread(self._password_hasher, password)
        if not isinstance(digest, str) or not 1 <= len(digest) <= 255:
            raise ValueError("password hasher returned an invalid storage value")
        try:
            async with self._factory() as session, session.begin():
                await self._lock_organization(session, organization_id)
                row = await self._create(
                    session,
                    organization_id,
                    normalized,
                    name,
                    digest,
                )
                await self._audit_creation(session, row, "password")
        except IntegrityError:
            raise HTTPException(409, "registration could not be completed") from None
        return account_view(row)

    async def google_account(self, organization_id, *, verified_identity):
        if not isinstance(verified_identity, Mapping):
            raise ValueError("verified Google identity required")
        if verified_identity.get("issuer") != GOOGLE_ISSUER:
            raise ValueError("Google issuer required")
        subject = verified_identity.get("subject")
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or len(subject) > 255
            or any(ord(character) < 32 or ord(character) == 127 for character in subject)
        ):
            raise ValueError("valid Google subject required")
        email, name = self._validate(
            organization_id,
            verified_identity.get("email"),
            verified_identity.get("full_name"),
        )
        try:
            async with self._factory() as session, session.begin():
                await self._lock_organization(session, organization_id)
                existing = (
                    (
                        await session.execute(
                            sa.select(
                                users.c.id,
                                users.c.organization_id,
                                users.c.full_name,
                                users.c.approval_status,
                                users.c.is_active,
                            )
                            .select_from(
                                identities.join(
                                    users,
                                    sa.and_(
                                        identities.c.user_id == users.c.id,
                                        identities.c.organization_id == users.c.organization_id,
                                    ),
                                )
                            )
                            .where(
                                identities.c.organization_id == organization_id,
                                identities.c.issuer == GOOGLE_ISSUER,
                                identities.c.subject == subject,
                            )
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing is not None:
                    if not existing["is_active"] or existing["approval_status"] not in {
                        "pending",
                        "approved",
                    }:
                        raise HTTPException(403, "account unavailable")
                    row = existing
                else:
                    row = await self._create(
                        session,
                        organization_id,
                        email,
                        name,
                        None,
                    )
                    await session.execute(
                        sa.insert(identities).values(
                            id=uuid4(),
                            organization_id=organization_id,
                            user_id=row["id"],
                            issuer=GOOGLE_ISSUER,
                            subject=subject,
                        )
                    )
                    await self._audit_creation(session, row, "google")
        except IntegrityError:
            raise HTTPException(409, "registration could not be completed") from None
        return account_view(row)
