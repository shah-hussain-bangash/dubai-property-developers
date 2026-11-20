"""Guarded PostgreSQL/Redis recovery transition.

Development-only. Not connected to the Docker worker.

This module serializes recovery-operation lease ownership checks
and Redis transitions by holding a PostgreSQL row lock.

IMPORTANT:
- PostgreSQL and Redis do not share a transaction.
- Redis transition evidence must be reconciled after crashes.
- The caller must authenticate the original job envelope first.
- This implementation supports retryable jobs only.
- Matching raw messages to envelopes is not origin authentication.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.redis_recovery_evidence import (
    recovery_evidence_key,
    requeue_with_evidence,
)
from database.models.background_job import BackgroundJob
from database.models.identity import Organization
from database.models.job_recovery_operation import JobRecoveryOperation


class GuardedRecoveryError(RuntimeError):
    """Recovery transition authorization or reconciliation failed."""


class GuardedRecoveryTransition:
    """Execute an ownership-guarded, evidence-backed retry transition."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def requeue(
        self,
        *,
        redis: Any,
        job: JobEnvelope,
        raw: str,
        operation_id: uuid.UUID,
        worker_id: str,
        lease_token: str,
        processing_key: str,
        pending_key: str,
        redis_timeout_seconds: float = 5.0,
    ) -> str:
        """Requeue only when the caller owns a valid recovery lease.

        The PostgreSQL recovery-operation row remains locked during
        the Redis transition, serializing participating coordinators
        with lease ownership updates.

        Returns:
            moved
            already_moved

        Missing and ambiguous outcomes raise GuardedRecoveryError.

        This function does not complete the PostgreSQL recovery
        operation or authenticate the original publication.
        """

        # Step 1: Validate the supplied job.
        if not isinstance(job, JobEnvelope):
            raise ValueError("JobEnvelope is required")

        # Step 2: Validate the raw Redis reservation.
        if not isinstance(raw, str) or not raw:
            raise ValueError("Raw Redis message is required")

        # Step 3: Parse the exact raw reservation into an envelope.
        try:
            received_job = JobEnvelope.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ValueError("Raw Redis message is not a valid JobEnvelope") from exc

        # Step 4: Ensure both supplied representations agree.
        # This does not replace encrypted-outbox authentication.
        if received_job != job:
            raise ValueError("Raw Redis message does not match authorized job")

        # Step 5: Validate the recovery-operation identity.
        if not isinstance(operation_id, uuid.UUID):
            raise ValueError("Valid operation_id is required")

        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id is required")

        if not isinstance(lease_token, str) or not lease_token.strip():
            raise ValueError("lease_token is required")

        # Step 6: Validate the Redis timeout.
        if (
            isinstance(redis_timeout_seconds, bool)
            or not isinstance(redis_timeout_seconds, (int, float))
            or not (0 < redis_timeout_seconds < float("inf"))
        ):
            raise ValueError("redis_timeout_seconds must be positive")

        evidence_key = recovery_evidence_key(operation_id)

        # Step 7: Open PostgreSQL transaction.
        async with self.session_factory() as session, session.begin():
            organization_id = await session.scalar(
                select(Organization.id).where(
                    Organization.slug == job.tenant_id,
                    Organization.is_active.is_(True),
                )
            )

            if organization_id is None:
                raise GuardedRecoveryError("Unknown or inactive organization")

            # Step 8: Lock the recovery operation row.
            # Lease updates on this row must wait until this
            # transaction releases the lock.
            operation = await session.scalar(
                select(JobRecoveryOperation)
                .where(
                    JobRecoveryOperation.id == operation_id,
                    JobRecoveryOperation.organization_id == organization_id,
                    JobRecoveryOperation.job_id == job.job_id,
                )
                .with_for_update(of=JobRecoveryOperation)
            )

            if operation is None:
                raise GuardedRecoveryError("Recovery operation does not match job")

            now = datetime.now(UTC)

            # Step 9: Verify current recovery lease ownership.
            if (
                operation.status != "processing"
                or operation.worker_id != worker_id
                or operation.lease_token != lease_token
                or operation.lease_expires_at is None
                or operation.lease_expires_at <= now
            ):
                raise GuardedRecoveryError("Recovery lease is not currently owned")

            # Step 10: Verify background-job eligibility.
            record = await session.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.organization_id == organization_id,
                    BackgroundJob.job_id == job.job_id,
                )
            )

            if (
                record is None
                or record.job_type != job.job_type
                or record.max_attempts != job.max_attempts
                or record.attempts != operation.job_attempt
                or record.status != "retrying"
                or record.attempts >= record.max_attempts
            ):
                raise GuardedRecoveryError("Background job is not eligible for requeue")

            # Step 11: Require sufficient remaining lease time.
            remaining_lease_seconds = (operation.lease_expires_at - now).total_seconds()

            if remaining_lease_seconds <= redis_timeout_seconds:
                raise GuardedRecoveryError("Insufficient recovery lease time")

            # Step 12: Execute atomic Redis requeue with evidence.
            try:
                result = await asyncio.wait_for(
                    requeue_with_evidence(
                        redis,
                        raw,
                        processing_key=processing_key,
                        pending_key=pending_key,
                        evidence_key=evidence_key,
                    ),
                    timeout=redis_timeout_seconds,
                )
            except TimeoutError as exc:
                raise GuardedRecoveryError("Redis recovery transition timed out") from exc

            # Step 13: Do not treat uncertain states as success.
            if result in {"missing", "ambiguous"}:
                raise GuardedRecoveryError(f"Redis reconciliation uncertain: {result}")

            return result
