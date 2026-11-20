"""Read-only PostgreSQL recovery coordinator authorization.

Development-only. Not connected to the Docker worker.

This module validates the relationship between:
- an authenticated background job,
- its PostgreSQL background-job record,
- the recovery operation,
- and the coordinator's current recovery lease.

Authorization is a point-in-time check, not a Redis fencing
mechanism. No queue mutation or recovery completion occurs here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker.jobs.envelope import JobEnvelope
from database.models.background_job import BackgroundJob
from database.models.identity import Organization
from database.models.job_recovery_operation import JobRecoveryOperation


class RecoveryAuthorizationError(ValueError):
    """Recovery operation authorization was rejected."""


class PostgresRedisRecoveryCoordinator:
    """Validate recovery ownership without changing application state."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def authorize(
        self,
        *,
        job: JobEnvelope,
        operation_id: uuid.UUID,
        worker_id: str,
        lease_token: str,
    ) -> str:
        """Validate a recovery operation and return its required action.

        Returns:
            requeue: retryable job requiring Redis reconciliation
            acknowledge: terminal failed job requiring cleanup

        This method accepts a job already authenticated by the
        PostgreSQL encrypted-outbox authenticator.

        The caller remains responsible for authenticating it.
        """

        if not isinstance(job, JobEnvelope):
            raise RecoveryAuthorizationError("Authenticated JobEnvelope is required")

        if not isinstance(operation_id, uuid.UUID):
            raise RecoveryAuthorizationError("Valid operation UUID is required")

        if not isinstance(worker_id, str) or not worker_id.strip():
            raise RecoveryAuthorizationError("worker_id is required")

        if not isinstance(lease_token, str) or not lease_token.strip():
            raise RecoveryAuthorizationError("lease_token is required")

        now = datetime.now(UTC)

        async with self.session_factory() as session:
            organization_id = await session.scalar(
                select(Organization.id).where(
                    Organization.slug == job.tenant_id,
                    Organization.is_active.is_(True),
                )
            )

            if organization_id is None:
                raise RecoveryAuthorizationError("Unknown or inactive organization")

            operation = await session.scalar(
                select(JobRecoveryOperation).where(
                    JobRecoveryOperation.id == operation_id,
                    JobRecoveryOperation.organization_id == organization_id,
                    JobRecoveryOperation.job_id == job.job_id,
                )
            )

            if operation is None:
                raise RecoveryAuthorizationError("Recovery operation does not match job")

            if (
                operation.status != "processing"
                or operation.worker_id != worker_id
                or operation.lease_token != lease_token
                or operation.lease_expires_at is None
                or operation.lease_expires_at <= now
            ):
                raise RecoveryAuthorizationError("Recovery lease is not currently owned")

            record = await session.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job.job_id,
                )
            )

            if record is None:
                raise RecoveryAuthorizationError("Background job registration missing")

            if (
                record.job_type != job.job_type
                or record.max_attempts != job.max_attempts
                or record.attempts != operation.job_attempt
            ):
                raise RecoveryAuthorizationError("Recovery metadata does not match job")

            if record.status == "retrying" and record.attempts < record.max_attempts:
                return "requeue"

            if record.status == "failed" and record.attempts >= record.max_attempts:
                return "acknowledge"

            raise RecoveryAuthorizationError("Background job is not eligible for recovery")
