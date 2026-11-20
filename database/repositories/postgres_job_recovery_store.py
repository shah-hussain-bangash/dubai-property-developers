"""Atomic PostgreSQL recovery of expired background-job leases.

This module changes only PostgreSQL job metadata.

It does NOT:
- Read, remove, or requeue Redis messages.
- Execute job handlers.
- Recover leases which are still active.

Redis reconciliation must be implemented separately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.background_job import BackgroundJob
from database.models.identity import Organization


class PostgresJobRecoveryStore:
    """Recover expired processing jobs under PostgreSQL row locks."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def recover_expired_lease(
        self,
        tenant_id: str,
        job_id: str,
        *,
        retry_delay_seconds: int = 0,
    ) -> str | None:
        """Atomically transition an expired processing job.

        Returns:
            "retrying": recovered and scheduled for retry
            "failed": attempts were already exhausted
            None: no eligible expired processing lease exists

        Row locking prevents two recovery processes from
        recovering the same lease simultaneously.

        This method does not requeue the Redis reservation.
        """

        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")

        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("job_id is required")

        if len(job_id) > 64:
            raise ValueError("job_id exceeds 64 characters")

        if not isinstance(retry_delay_seconds, int) or retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be nonnegative")

        async with self.session_factory() as session, session.begin():
            record = await session.scalar(
                select(BackgroundJob)
                .join(
                    Organization,
                    Organization.id == BackgroundJob.organization_id,
                )
                .where(
                    Organization.slug == tenant_id,
                    Organization.is_active.is_(True),
                    BackgroundJob.job_id == job_id,
                )
                .with_for_update(of=BackgroundJob)
            )

            if record is None:
                return None

            # Evaluate expiry after obtaining the row lock.
            # Another worker may have renewed the lease
            # while this transaction was waiting.
            now = datetime.now(UTC)

            if (
                record.status != "processing"
                or record.lease_expires_at is None
                or record.lease_expires_at > now
            ):
                return None

            exhausted = record.attempts >= record.max_attempts

            # Invalidate the original worker's ownership.
            record.worker_id = None
            record.lease_token = None
            record.lease_expires_at = None
            record.error_code = "timeout"

            if exhausted:
                record.status = "failed"
                record.next_retry_at = None
                record.finished_at = now
                return "failed"

            record.status = "retrying"
            record.next_retry_at = now + timedelta(seconds=retry_delay_seconds)
            record.finished_at = None

            return "retrying"
