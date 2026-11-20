"""PostgreSQL ownership leases for durable recovery operations.

Development-only. Does not modify Redis or execute job handlers.

Operations may be:
- pending: awaiting a coordinator
- processing: owned by a coordinator
- retrying: temporarily failed, waiting for retry
- completed: reconciliation confirmed

An expired processing lease may be reclaimed, but Redis recovery
must not begin until cross-system coordination is implemented.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.identity import Organization
from database.models.job_recovery_operation import JobRecoveryOperation


@dataclass(frozen=True, slots=True)
class RecoveryLeaseClaim:
    lease_token: str
    generation: int


class PostgresRecoveryLeaseStore:
    """Manage tenant-scoped recovery-operation ownership."""

    SAFE_ERRORS = {
        "redis_unavailable",
        "reconciliation_error",
        "timeout",
        "authentication_error",
    }

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _validate(
        tenant_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required")

        if not worker_id or not worker_id.strip():
            raise ValueError("worker_id is required")

        if len(worker_id) > 128:
            raise ValueError("worker_id exceeds 128 characters")

        if type(lease_seconds) is not int or lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")

    async def claim(
        self,
        tenant_id: str,
        operation_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 120,
    ) -> str | None:
        """Preserve the existing token-only API."""
        result = await self.claim_with_generation(
            tenant_id,
            operation_id,
            worker_id,
            lease_seconds=lease_seconds,
        )
        return result.lease_token if result is not None else None

    async def claim_with_generation(
        self,
        tenant_id: str,
        operation_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 120,
    ) -> RecoveryLeaseClaim | None:
        """Atomically claim an eligible recovery operation.

        Returns a new ownership token, or None if unavailable.
        """

        self._validate(tenant_id, worker_id, lease_seconds)

        now = datetime.now(UTC)
        token = uuid.uuid4().hex

        async with self.session_factory() as session, session.begin():
            organization_id = await session.scalar(
                select(Organization.id).where(
                    Organization.slug == tenant_id,
                    Organization.is_active.is_(True),
                )
            )

            if organization_id is None:
                return None

            statement = (
                update(JobRecoveryOperation)
                .where(
                    JobRecoveryOperation.id == operation_id,
                    JobRecoveryOperation.organization_id == organization_id,
                    or_(
                        JobRecoveryOperation.status == "pending",
                        (
                            (JobRecoveryOperation.status == "retrying")
                            & or_(
                                JobRecoveryOperation.next_attempt_at.is_(None),
                                JobRecoveryOperation.next_attempt_at <= now,
                            )
                        ),
                        (
                            (JobRecoveryOperation.status == "processing")
                            & JobRecoveryOperation.lease_expires_at.is_not(None)
                            & (JobRecoveryOperation.lease_expires_at <= now)
                        ),
                    ),
                )
                .values(
                    status="processing",
                    worker_id=worker_id,
                    lease_token=token,
                    lease_expires_at=(now + timedelta(seconds=lease_seconds)),
                    next_attempt_at=None,
                    attempts=JobRecoveryOperation.attempts + 1,
                )
                .returning(JobRecoveryOperation.attempts)
            )

            generation = await session.scalar(statement)
            return (
                RecoveryLeaseClaim(lease_token=token, generation=generation)
                if generation is not None
                else None
            )

    async def heartbeat(
        self,
        tenant_id: str,
        operation_id: uuid.UUID,
        worker_id: str,
        lease_token: str,
        *,
        lease_seconds: int = 120,
    ) -> bool:
        """Renew only a valid lease owned by the caller."""

        self._validate(tenant_id, worker_id, lease_seconds)

        if not lease_token:
            raise ValueError("lease_token is required")

        now = datetime.now(UTC)

        async with self.session_factory() as session, session.begin():
            organization_id = await session.scalar(
                select(Organization.id).where(
                    Organization.slug == tenant_id,
                    Organization.is_active.is_(True),
                )
            )

            if organization_id is None:
                return False

            statement = (
                update(JobRecoveryOperation)
                .where(
                    JobRecoveryOperation.id == operation_id,
                    JobRecoveryOperation.organization_id == organization_id,
                    JobRecoveryOperation.status == "processing",
                    JobRecoveryOperation.worker_id == worker_id,
                    JobRecoveryOperation.lease_token == lease_token,
                    JobRecoveryOperation.lease_expires_at > now,
                )
                .values(lease_expires_at=(now + timedelta(seconds=lease_seconds)))
                .returning(JobRecoveryOperation.id)
            )

            return await session.scalar(statement) is not None

    async def complete(
        self,
        tenant_id: str,
        operation_id: uuid.UUID,
        worker_id: str,
        lease_token: str,
    ) -> bool:
        """Finish an operation only while its lease is valid."""

        self._validate(tenant_id, worker_id, 1)

        if not lease_token:
            raise ValueError("lease_token is required")

        now = datetime.now(UTC)

        async with self.session_factory() as session, session.begin():
            organization_id = await session.scalar(
                select(Organization.id).where(
                    Organization.slug == tenant_id,
                    Organization.is_active.is_(True),
                )
            )

            if organization_id is None:
                return False

            statement = (
                update(JobRecoveryOperation)
                .where(
                    JobRecoveryOperation.id == operation_id,
                    JobRecoveryOperation.organization_id == organization_id,
                    JobRecoveryOperation.status == "processing",
                    JobRecoveryOperation.worker_id == worker_id,
                    JobRecoveryOperation.lease_token == lease_token,
                    JobRecoveryOperation.lease_expires_at > now,
                )
                .values(
                    status="completed",
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    next_attempt_at=None,
                    completed_at=now,
                    error_code=None,
                )
                .returning(JobRecoveryOperation.id)
            )

            return await session.scalar(statement) is not None

    async def fail(
        self,
        tenant_id: str,
        operation_id: uuid.UUID,
        worker_id: str,
        lease_token: str,
        *,
        retry_delay_seconds: int = 30,
        error_code: str = "reconciliation_error",
    ) -> bool:
        """Schedule another attempt after a coordinator failure."""

        self._validate(tenant_id, worker_id, 1)

        if not lease_token:
            raise ValueError("lease_token is required")

        if type(retry_delay_seconds) is not int or retry_delay_seconds < 0:
            raise ValueError("Invalid retry_delay_seconds")

        if error_code not in self.SAFE_ERRORS:
            error_code = "reconciliation_error"

        now = datetime.now(UTC)

        async with self.session_factory() as session, session.begin():
            organization_id = await session.scalar(
                select(Organization.id).where(
                    Organization.slug == tenant_id,
                    Organization.is_active.is_(True),
                )
            )

            if organization_id is None:
                return False

            statement = (
                update(JobRecoveryOperation)
                .where(
                    JobRecoveryOperation.id == operation_id,
                    JobRecoveryOperation.organization_id == organization_id,
                    JobRecoveryOperation.status == "processing",
                    JobRecoveryOperation.worker_id == worker_id,
                    JobRecoveryOperation.lease_token == lease_token,
                    JobRecoveryOperation.lease_expires_at > now,
                )
                .values(
                    status="retrying",
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    next_attempt_at=(now + timedelta(seconds=retry_delay_seconds)),
                    error_code=error_code,
                )
                .returning(JobRecoveryOperation.id)
            )

            return await session.scalar(statement) is not None
