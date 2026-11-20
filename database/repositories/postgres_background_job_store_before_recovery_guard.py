"""PostgreSQL persistence for background-job lifecycle metadata.

Supports:
- Tenant-scoped registration
- Atomic worker claims
- Processing lease heartbeats
- Lease-protected completion and failure
- Retry scheduling
- Expired lease discovery

Redis reservation reconciliation and automatic crash recovery
are implemented separately.

No raw job payloads or customer PII are stored here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.background_job import BackgroundJob
from database.models.identity import Organization


class PostgresBackgroundJobStore:
    """Tenant-scoped PostgreSQL background-job repository."""

    SAFE_ERROR_CODES = {
        "job_error",
        "handler_error",
        "timeout",
        "validation_error",
        "external_unavailable",
    }

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("job_id is required")
        if len(job_id) > 64:
            raise ValueError("job_id exceeds 64 characters")

    @staticmethod
    def _validate_worker_id(worker_id: str) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id is required")
        if len(worker_id) > 128:
            raise ValueError("worker_id exceeds 128 characters")

    async def _organization_id(
        self,
        session: AsyncSession,
        tenant_id: str,
    ) -> uuid.UUID:
        """Resolve an active tenant by its organization slug."""

        if not tenant_id:
            raise ValueError("tenant_id is required")

        organization_id = await session.scalar(
            select(Organization.id).where(
                Organization.slug == tenant_id,
                Organization.is_active.is_(True),
            )
        )

        if organization_id is None:
            raise ValueError(f"Unknown or inactive organization: {tenant_id}")

        return organization_id

    async def register(
        self,
        tenant_id: str,
        job_id: str,
        job_type: str,
        *,
        max_attempts: int = 3,
        correlation_id: str | None = None,
    ) -> BackgroundJob:
        """Register a job without duplicating an existing tenant/job ID.

        PostgreSQL ON CONFLICT handles simultaneous registration.
        An existing job must keep its original type and retry limit.
        """

        self._validate_job_id(job_id)

        if not job_type or len(job_type) > 64:
            raise ValueError("Invalid job_type")

        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        if correlation_id is not None and len(correlation_id) > 64:
            raise ValueError("correlation_id exceeds 64 characters")

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                pg_insert(BackgroundJob)
                .values(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    job_id=job_id,
                    job_type=job_type,
                    status="pending",
                    attempts=0,
                    max_attempts=max_attempts,
                    correlation_id=correlation_id,
                )
                .on_conflict_do_nothing(constraint="uq_background_jobs_org_job_id")
            )

            await session.execute(statement)

            record = await session.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job_id,
                )
            )

            if record is None:
                raise RuntimeError("Job registration failed")

            if record.job_type != job_type or record.max_attempts != max_attempts:
                raise ValueError("Existing job registration cannot be changed")

            return record

    async def get(
        self,
        tenant_id: str,
        job_id: str,
    ) -> BackgroundJob | None:
        """Retrieve job metadata within one tenant."""

        self._validate_job_id(job_id)

        async with self.session_factory() as session:
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            return cast(
                BackgroundJob | None,
                await session.scalar(
                    select(BackgroundJob).where(
                        BackgroundJob.organization_id == organization_id,
                        BackgroundJob.job_id == job_id,
                    )
                ),
            )

    async def claim(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 120,
    ) -> str | None:
        """Atomically claim an eligible job.

        Returns a new lease token on success, otherwise None.

        Eligible jobs:
            pending
            retrying, when next_retry_at has elapsed

        Expired processing jobs require explicit recovery handling.
        """

        self._validate_job_id(job_id)
        self._validate_worker_id(worker_id)

        if not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")

        now = datetime.now(UTC)
        token = uuid.uuid4().hex

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                update(BackgroundJob)
                .where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job_id,
                    BackgroundJob.attempts < BackgroundJob.max_attempts,
                    or_(
                        BackgroundJob.status == "pending",
                        (
                            (BackgroundJob.status == "retrying")
                            & or_(
                                BackgroundJob.next_retry_at.is_(None),
                                BackgroundJob.next_retry_at <= now,
                            )
                        ),
                    ),
                )
                .values(
                    status="processing",
                    worker_id=worker_id,
                    lease_token=token,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    next_retry_at=None,
                    attempts=BackgroundJob.attempts + 1,
                    started_at=func.coalesce(
                        BackgroundJob.started_at,
                        now,
                    ),
                )
                .returning(BackgroundJob.id)
            )

            claimed_id = await session.scalar(statement)

            return token if claimed_id is not None else None

    async def heartbeat(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        *,
        lease_seconds: int = 120,
    ) -> bool:
        """Renew a currently valid processing lease."""

        self._validate_job_id(job_id)
        self._validate_worker_id(worker_id)

        if not lease_token:
            raise ValueError("lease_token is required")

        if not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")

        now = datetime.now(UTC)

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                update(BackgroundJob)
                .where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job_id,
                    BackgroundJob.status == "processing",
                    BackgroundJob.worker_id == worker_id,
                    BackgroundJob.lease_token == lease_token,
                    BackgroundJob.lease_expires_at > now,
                )
                .values(
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                .returning(BackgroundJob.id)
            )

            updated_id = await session.scalar(statement)

            return updated_id is not None

    async def complete(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
    ) -> bool:
        """Complete only when the caller owns a valid lease."""

        self._validate_job_id(job_id)
        self._validate_worker_id(worker_id)

        if not lease_token:
            raise ValueError("lease_token is required")

        now = datetime.now(UTC)

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            statement = (
                update(BackgroundJob)
                .where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job_id,
                    BackgroundJob.status == "processing",
                    BackgroundJob.worker_id == worker_id,
                    BackgroundJob.lease_token == lease_token,
                    BackgroundJob.lease_expires_at > now,
                )
                .values(
                    status="succeeded",
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    next_retry_at=None,
                    error_code=None,
                    finished_at=now,
                )
                .returning(BackgroundJob.id)
            )

            updated_id = await session.scalar(statement)

            return updated_id is not None

    async def fail(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        *,
        retry_delay_seconds: int = 30,
        error_code: str = "job_error",
    ) -> str | None:
        """Record a failed attempt under the current valid lease.

        Returns:
            "retrying" - retry is scheduled
            "failed"   - retry attempts exhausted
            None       - lease not owned or no longer valid

        The caller must separately reconcile the Redis reservation.
        """

        self._validate_job_id(job_id)
        self._validate_worker_id(worker_id)

        if not lease_token:
            raise ValueError("lease_token is required")

        if not isinstance(retry_delay_seconds, int) or retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be >= 0")

        if error_code not in self.SAFE_ERROR_CODES:
            error_code = "job_error"

        now = datetime.now(UTC)

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            record = await session.scalar(
                select(BackgroundJob)
                .where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job_id,
                )
                .with_for_update()
            )

            if record is None:
                return None

            if (
                record.status != "processing"
                or record.worker_id != worker_id
                or record.lease_token != lease_token
                or record.lease_expires_at is None
                or record.lease_expires_at <= now
            ):
                return None

            exhausted = record.attempts >= record.max_attempts

            record.status = "failed" if exhausted else "retrying"

            record.worker_id = None
            record.lease_token = None
            record.lease_expires_at = None
            record.error_code = error_code

            if exhausted:
                record.next_retry_at = None
                record.finished_at = now
            else:
                record.next_retry_at = now + timedelta(seconds=retry_delay_seconds)
                record.finished_at = None

            return record.status

    async def list_expired(
        self,
        *,
        limit: int = 100,
    ) -> list[BackgroundJob]:
        """Find processing jobs whose leases have expired.

        Read-only. This method does not requeue or claim jobs.
        Recovery must use additional synchronization safeguards.
        """

        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")

        now = datetime.now(UTC)

        async with self.session_factory() as session:
            records = await session.scalars(
                select(BackgroundJob)
                .where(
                    BackgroundJob.status == "processing",
                    BackgroundJob.lease_expires_at.is_not(None),
                    BackgroundJob.lease_expires_at <= now,
                )
                .order_by(
                    BackgroundJob.lease_expires_at,
                    BackgroundJob.id,
                )
                .limit(limit)
            )

            return list(records.all())
