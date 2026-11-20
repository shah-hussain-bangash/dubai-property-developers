"""Experimental PostgreSQL tool execution claim repository.

This module is not connected to the active ToolGateway or worker.

Claims are acquired using PostgreSQL's unique constraint.
Completed and uncertain states cannot automatically be reclaimed.

This does not guarantee exactly-once external API side effects.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.identity import Organization
from database.models.tool_execution import ToolExecutionLedger


class PostgresToolExecutionClaimStore:
    """Tenant-scoped, durable execution ownership repository."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _validate_tenant(tenant_id: str) -> None:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not 0 < len(key) <= 256:
            raise ValueError("Invalid idempotency key")

    @staticmethod
    def _validate_tool(tool_name: str) -> None:
        if not isinstance(tool_name, str) or not tool_name.strip() or len(tool_name) > 128:
            raise ValueError("Invalid tool name")

    @staticmethod
    def _validate_owner(owner_token: str) -> None:
        if not isinstance(owner_token, str) or not owner_token.strip() or len(owner_token) > 64:
            raise ValueError("Invalid execution owner token")

    @staticmethod
    async def _organization_id(
        session: AsyncSession,
        tenant_id: str,
    ) -> uuid.UUID:
        organization_id = await session.scalar(
            select(Organization.id).where(
                Organization.slug == tenant_id,
                Organization.is_active.is_(True),
            )
        )

        if organization_id is None:
            raise ValueError(f"Unknown or inactive organization: {tenant_id}")

        return organization_id

    async def claim(
        self,
        tenant_id: str,
        key: str,
        tool_name: str,
        request_fingerprint: str,
    ) -> str | None:
        """Atomically acquire a new execution claim.

        Returns the owner token when the claim is acquired.
        Returns None if this tenant/key already has a claim.

        Existing claims are never automatically overwritten,
        regardless of their state or age.
        """

        self._validate_tenant(tenant_id)
        self._validate_key(key)
        self._validate_tool(tool_name)

        if (
            not isinstance(request_fingerprint, str)
            or len(request_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in request_fingerprint)
        ):
            raise ValueError("Invalid SHA-256 request fingerprint")

        owner_token = uuid.uuid4().hex

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                pg_insert(ToolExecutionLedger)
                .values(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    idempotency_key=key,
                    tool_name=tool_name,
                    request_fingerprint=request_fingerprint,
                    state="in_progress",
                    owner_token=owner_token,
                    claimed_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(constraint="uq_tool_execution_ledger_org_key")
                .returning(ToolExecutionLedger.id)
            )

            created_id = await session.scalar(statement)

            if created_id is None:
                return None

            return owner_token

    async def get(
        self,
        tenant_id: str,
        key: str,
    ) -> ToolExecutionLedger | None:
        """Read a claim belonging to the specified active tenant."""

        self._validate_tenant(tenant_id)
        self._validate_key(key)

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            record = await session.scalar(
                select(ToolExecutionLedger).where(
                    ToolExecutionLedger.organization_id == organization_id,
                    ToolExecutionLedger.idempotency_key == key,
                )
            )

            return record

    async def complete(
        self,
        tenant_id: str,
        key: str,
        owner_token: str,
        result: dict[str, Any],
    ) -> bool:
        """Complete a claim only when the owner and state match.

        Returns True when the transition commits.
        Returns False if no matching in-progress claim exists.
        """

        self._validate_tenant(tenant_id)
        self._validate_key(key)
        self._validate_owner(owner_token)

        if not isinstance(result, dict):
            raise ValueError("result must be a dictionary")

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                update(ToolExecutionLedger)
                .where(
                    ToolExecutionLedger.organization_id == organization_id,
                    ToolExecutionLedger.idempotency_key == key,
                    ToolExecutionLedger.owner_token == owner_token,
                    ToolExecutionLedger.state == "in_progress",
                )
                .values(
                    state="completed",
                    result_json=dict(result),
                    completed_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                .returning(ToolExecutionLedger.id)
            )

            changed_id = await session.scalar(statement)

            return changed_id is not None

    async def mark_uncertain(
        self,
        tenant_id: str,
        key: str,
        owner_token: str,
    ) -> bool:
        """Block automatic re-execution of an uncertain action.

        Returns True when the transition commits.
        Returns False if ownership or state no longer matches.
        """

        self._validate_tenant(tenant_id)
        self._validate_key(key)
        self._validate_owner(owner_token)

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                update(ToolExecutionLedger)
                .where(
                    ToolExecutionLedger.organization_id == organization_id,
                    ToolExecutionLedger.idempotency_key == key,
                    ToolExecutionLedger.owner_token == owner_token,
                    ToolExecutionLedger.state == "in_progress",
                )
                .values(
                    state="uncertain",
                    updated_at=datetime.now(UTC),
                )
                .returning(ToolExecutionLedger.id)
            )

            changed_id = await session.scalar(statement)

            return changed_id is not None

    async def list_unresolved(
        self,
        tenant_id: str,
        limit: int = 50,
        *,
        after: tuple[datetime, UUID] | None = None,
    ) -> list[ToolExecutionLedger]:
        """Read unresolved claims without modifying their state."""

        from datetime import datetime
        from uuid import UUID

        from sqlalchemy import select, tuple_

        self._validate_tenant(tenant_id)

        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")

        if after is not None and (
            not isinstance(after, tuple)
            or len(after) != 2
            or not isinstance(after[0], datetime)
            or after[0].tzinfo is None
            or after[0].utcoffset() is None
            or not isinstance(after[1], UUID)
        ):
            raise ValueError("after must be an aware datetime and UUID tuple")

        async with self.session_factory() as session:
            organization_id = await self._organization_id(session, tenant_id)

            statement = select(ToolExecutionLedger).where(
                ToolExecutionLedger.organization_id == organization_id,
                ToolExecutionLedger.state.in_(("in_progress", "uncertain")),
            )

            if after is not None:
                statement = statement.where(
                    tuple_(
                        ToolExecutionLedger.claimed_at,
                        ToolExecutionLedger.id,
                    )
                    > tuple_(literal(after[0]), literal(after[1]))
                )

            statement = statement.order_by(
                ToolExecutionLedger.claimed_at.asc(),
                ToolExecutionLedger.id.asc(),
            ).limit(limit)

            result = await session.execute(statement)
            return list(result.scalars().all())
