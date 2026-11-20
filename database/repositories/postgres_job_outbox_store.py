
"""Transactional, encrypted PostgreSQL job publisher.

Atomically creates:
    1. A background_jobs tracking record.
    2. A job_outbox encrypted publication record.

This module does not publish to Redis. Delivery and recovery
belong to the outbox dispatcher.

Repeated submission of an identical job is idempotent.
Conflicting submissions using the same tenant/job ID are rejected.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker.jobs.envelope import JobEnvelope
from core.security.job_encryption import JobEnvelopeCipher
from database.models.background_job import BackgroundJob
from database.models.identity import Organization
from database.models.job_outbox import JobOutbox


class PostgresJobOutboxStore:
    """Persist a background job and encrypted outbox entry together."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: JobEnvelopeCipher,
    ) -> None:
        self.session_factory = session_factory
        self.cipher = cipher

    @staticmethod
    def _validate_job(job: JobEnvelope) -> None:
        if not job.tenant_id or not job.tenant_id.strip():
            raise ValueError("tenant_id is required")

        if not job.job_id or len(job.job_id) > 64:
            raise ValueError("Invalid job_id")

        if not job.job_type or len(job.job_type) > 64:
            raise ValueError("Invalid job_type")

        if job.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        if job.attempts != 0:
            raise ValueError(
                "Only new jobs with zero attempts can be published"
            )

        if (
            job.correlation_id is not None
            and len(job.correlation_id) > 64
        ):
            raise ValueError("correlation_id exceeds 64 characters")

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
            raise ValueError(
                f"Unknown or inactive organization: {tenant_id}"
            )

        return organization_id

    async def publish(self, job: JobEnvelope) -> str:
        """Durably register a new encrypted job for future dispatch.

        Returns the job ID.

        Both database inserts commit together. A database failure
        rolls back the entire transaction.

        An identical repeated submission preserves the original
        outbox record rather than creating another publication.
        """

        self._validate_job(job)

        encrypted_payload, key_id = self.cipher.encrypt(job)

        async with self.session_factory() as session:
            async with session.begin():
                organization_id = await self._organization_id(
                    session,
                    job.tenant_id,
                )

                # Concurrent attempts to register the same job are
                # serialized by PostgreSQL's unique constraint.
                job_insert = (
                    pg_insert(BackgroundJob)
                    .values(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        job_id=job.job_id,
                        job_type=job.job_type,
                        status="pending",
                        attempts=0,
                        max_attempts=job.max_attempts,
                        correlation_id=job.correlation_id,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_background_jobs_org_job_id"
                    )
                )

                await session.execute(job_insert)

                existing_job = await session.scalar(
                    select(BackgroundJob)
                    .where(
                        BackgroundJob.organization_id
                        == organization_id,
                        BackgroundJob.job_id == job.job_id,
                    )
                    .with_for_update()
                )

                if existing_job is None:
                    raise RuntimeError(
                        "Background job registration failed"
                    )

                if (
                    existing_job.job_type != job.job_type
                    or existing_job.max_attempts != job.max_attempts
                    or existing_job.correlation_id
                    != job.correlation_id
                ):
                    raise ValueError(
                        "Conflicting background job registration"
                    )

                outbox_insert = (
                    pg_insert(JobOutbox)
                    .values(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        job_id=job.job_id,
                        payload_ciphertext=encrypted_payload,
                        encryption_key_id=key_id,
                        status="pending",
                        publish_attempts=0,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_job_outbox_org_job_id"
                    )
                )

                await session.execute(outbox_insert)

                existing_outbox = await session.scalar(
                    select(JobOutbox)
                    .where(
                        JobOutbox.organization_id
                        == organization_id,
                        JobOutbox.job_id == job.job_id,
                    )
                    .with_for_update()
                )

                if existing_outbox is None:
                    raise RuntimeError(
                        "Encrypted outbox registration failed"
                    )

                # Authenticate the saved envelope. A same-ID
                # submission with different content must not silently
                # overwrite the original publication.
                saved_job = self.cipher.decrypt(
                    existing_outbox.payload_ciphertext,
                    existing_outbox.encryption_key_id,
                    tenant_id=job.tenant_id,
                    job_id=job.job_id,
                )

                if saved_job != job:
                    raise ValueError(
                        "Conflicting job payload for existing job ID"
                    )

        return job.job_id
