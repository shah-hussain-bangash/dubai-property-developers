
"""Durable registration of expired-job recovery operations.

Recovery of the background job and creation of its tracking
operation take place in a single PostgreSQL transaction.

This module does NOT modify Redis, execute handlers, or start
automatic recovery. It is not wired into the Docker worker.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.background_job import BackgroundJob
from database.models.identity import Organization
from database.models.job_recovery_operation import JobRecoveryOperation


class PostgresJobRecoveryOperationStore:
    """Register expired-lease recoveries transactionally."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def begin_expired_recovery(
        self,
        tenant_id: str,
        job_id: str,
        *,
        retry_delay_seconds: int = 0,
    ) -> uuid.UUID | None:
        """Recover an expired lease and create its operation.

        Returns:
            UUID: newly created recovery operation
            None: no eligible expired processing lease

        The background job row is locked throughout the
        transaction. Concurrent coordinators cannot register
        the same recovery attempt twice.

        The operation is left pending for future Redis
        reconciliation. No Redis action occurs here.
        """

        if (
            not isinstance(tenant_id, str)
            or not tenant_id.strip()
        ):
            raise ValueError("tenant_id is required")

        if (
            not isinstance(job_id, str)
            or not job_id.strip()
            or len(job_id) > 64
        ):
            raise ValueError("Invalid job_id")

        if (
            type(retry_delay_seconds) is not int
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be nonnegative"
            )

        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(BackgroundJob)
                    .join(
                        Organization,
                        Organization.id
                        == BackgroundJob.organization_id,
                    )
                    .where(
                        Organization.slug == tenant_id,
                        Organization.is_active.is_(True),
                        BackgroundJob.job_id == job_id,
                    )
                    .with_for_update(of=BackgroundJob)
                )

                if job is None:
                    return None

                # Evaluate expiry after acquiring the row lock.
                # A heartbeat may have renewed the lease while
                # this transaction waited.
                now = datetime.now(UTC)

                if (
                    job.status != "processing"
                    or job.lease_expires_at is None
                    or job.lease_expires_at > now
                ):
                    return None

                if job.attempts < 1:
                    raise RuntimeError(
                        "Processing job has no recorded attempt"
                    )

                operation_id = uuid.uuid4()

                operation = JobRecoveryOperation(
                    id=operation_id,
                    organization_id=job.organization_id,
                    job_id=job.job_id,
                    job_attempt=job.attempts,
                    status="pending",
                    attempts=0,
                )

                # Create the recovery record in the SAME
                # transaction as the job state transition.
                session.add(operation)

                exhausted = job.attempts >= job.max_attempts

                # Invalidate the original worker's ownership.
                job.worker_id = None
                job.lease_token = None
                job.lease_expires_at = None
                job.error_code = "timeout"

                if exhausted:
                    job.status = "failed"
                    job.next_retry_at = None
                    job.finished_at = now
                else:
                    job.status = "retrying"
                    job.next_retry_at = (
                        now
                        + timedelta(
                            seconds=retry_delay_seconds
                        )
                    )
                    job.finished_at = None

                # Both changes commit together. A failure
                # rolls back both the job and the operation.
                await session.flush()

                return operation_id
