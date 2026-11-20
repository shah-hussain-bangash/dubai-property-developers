
"""Authenticate Redis jobs against their encrypted PostgreSQL outbox.

A Redis job is untrusted until its complete envelope matches the
original encrypted publication record.

This component does not execute handlers or modify queue state.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker.jobs.envelope import JobEnvelope
from core.security.job_encryption import (
    JobEncryptionError,
    JobEnvelopeCipher,
)
from database.models.identity import Organization
from database.models.job_outbox import JobOutbox


class JobPayloadAuthenticationError(ValueError):
    """A Redis job failed origin or payload verification."""


class PostgresJobPayloadAuthenticator:
    """Verify Redis messages using PostgreSQL encrypted originals."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: JobEnvelopeCipher,
    ) -> None:
        self.session_factory = session_factory
        self.cipher = cipher

    async def authenticate(self, job: JobEnvelope) -> JobEnvelope:
        """Return the authenticated original, or reject the message.

        No job is trusted merely because its ID and tenant match.
        """

        if not job.tenant_id or not job.job_id:
            raise JobPayloadAuthenticationError(
                "Missing job identity"
            )

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(
                        JobOutbox.payload_ciphertext,
                        JobOutbox.encryption_key_id,
                    )
                    .join(
                        Organization,
                        Organization.id
                        == JobOutbox.organization_id,
                    )
                    .where(
                        Organization.slug == job.tenant_id,
                        Organization.is_active.is_(True),
                        JobOutbox.job_id == job.job_id,
                    )
                )
            ).one_or_none()

        if row is None:
            raise JobPayloadAuthenticationError(
                "Encrypted job publication not found"
            )

        ciphertext, key_id = row

        try:
            original = self.cipher.decrypt(
                bytes(ciphertext),
                key_id,
                tenant_id=job.tenant_id,
                job_id=job.job_id,
            )
        except JobEncryptionError as exc:
            raise JobPayloadAuthenticationError(
                "Encrypted job authentication failed"
            ) from exc

        # Compare the entire original envelope, including payload.
        # PostgreSQL remains authoritative for processing attempts;
        # the new worker must use the original publication envelope,
        # not mutate its Redis delivery copy.
        if original != job:
            raise JobPayloadAuthenticationError(
                "Redis job differs from authenticated publication"
            )

        return original
