"""Authentication orchestration awaiting trusted application composition.

No engines, routes, configuration files, or project modules are loaded.
Supply reviewed dependencies and a dummy hash generated with the real hasher.
Public routes must supply server-selected organization IDs and apply rate limits.
"""
import asyncio
from uuid import UUID

import sqlalchemy as sa
from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException

users = sa.table(
    "users",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("email", sa.String(254)),
    sa.column("password_hash", sa.String(255)),
    sa.column("is_active", sa.Boolean()),
    sa.column("approval_status", sa.String(16)),
)
organizations = sa.table(
    "organizations",
    sa.column("id", sa.Uuid()),
    sa.column("is_active", sa.Boolean()),
)

class AccountAuthentication:
    def __init__(
        self, session_factory, *, password_verifier, dummy_hash,
        registration_service, session_service, google_provider,
    ):
        if not callable(session_factory) or not callable(password_verifier):
            raise ValueError("trusted database factory and verifier required")
        if not isinstance(dummy_hash, str) or not 1 <= len(dummy_hash) <= 255:
            raise ValueError("dummy hash from the reviewed hasher required")
        self._factory = session_factory
        self._verify_password = password_verifier
        self._dummy_hash = dummy_hash
        self._registration = registration_service
        self._sessions = session_service
        self._google = google_provider

    def _organization(self, organization_id):
        if not isinstance(organization_id, UUID) or organization_id.int == 0:
            raise ValueError("trusted organization UUID required")

    async def login_password(self, organization_id, *, email, password):
        self._organization(organization_id)
        if (
            not isinstance(email, str) or len(email) > 254
            or not isinstance(password, str) or len(password) > 1024
        ):
            raise HTTPException(401, "invalid sign-in")
        try:
            normalized = validate_email(
                email, check_deliverability=False,
            ).normalized
        except EmailNotValidError:
            raise HTTPException(401, "invalid sign-in") from None

        statement = (
            sa.select(
                users.c.id, users.c.organization_id, users.c.password_hash,
                users.c.is_active, users.c.approval_status,
            )
            .select_from(users.join(
                organizations, users.c.organization_id == organizations.c.id,
            ))
            .where(
                users.c.organization_id == organization_id,
                users.c.email == normalized,
                organizations.c.is_active.is_(True),
            )
            .with_for_update(read=True)
        )
        async with self._factory() as session:
            async with session.begin():
                row = (await session.execute(statement)).mappings().first()
                stored = row["password_hash"] if row is not None else None
                usable = isinstance(stored, str) and bool(stored)
                digest = stored if usable else self._dummy_hash
                try:
                    valid = await asyncio.to_thread(
                        self._verify_password, password, digest,
                    )
                except (ValueError, TypeError, UnicodeError, OverflowError):
                    valid = False
                if (
                    valid is not True or row is None or not usable
                    or row["is_active"] is not True
                    or row["approval_status"] not in {"pending", "approved"}
                ):
                    raise HTTPException(401, "invalid sign-in")
                user_id = row["id"]
                tenant_id = row["organization_id"]

        # Session service rechecks current account and organization eligibility.
        return await self._sessions.issue_authenticated(
            user_id, tenant_id, auth_method="password",
        )

    async def register_password(self, organization_id, **credentials):
        self._organization(organization_id)
        return await self._registration.register_password(
            organization_id, **credentials,
        )

    async def login_google(self, organization_id, *, request):
        self._organization(organization_id)
        identity = await self._google.complete(request)
        account = await self._registration.google_account(
            organization_id, verified_identity=identity,
        )
        if account["organization_id"] != organization_id:
            raise HTTPException(403, "account access denied")
        return await self._sessions.issue_authenticated(
            account["account_id"], organization_id, auth_method="google",
        )

    async def logout(self, token):
        return await self._sessions.revoke(token)
