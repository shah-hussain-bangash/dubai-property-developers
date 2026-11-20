
"""Single-attempt PostgreSQL-to-Redis outbox dispatcher.

This module does not start a background process.

It is deliberately not integrated into the running worker yet.
Consumer-side PostgreSQL claims and duplicate-delivery protection
must be implemented before enabling automatic dispatch.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker.jobs.envelope import enqueue
from core.security.job_encryption import (
    JobEncryptionError,
    JobEnvelopeCipher,
)
from database.models.identity import Organization
from database.repositories.postgres_outbox_dispatch_store import (
    ClaimedOutboxMessage,
    PostgresOutboxDispatchStore,
)


class OutboxDispatcher:
    """Publish one leased outbox message per invocation."""

    def __init__(
        self,
        dispatch_store: PostgresOutboxDispatchStore,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: JobEnvelopeCipher,
        redis: Any,
        *,
        worker_id: str,
        lease_seconds: int = 120,
        retry_delay_seconds: int = 30,
    ) -> None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("Invalid dispatcher worker_id")

        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")

        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")

        self.dispatch_store = dispatch_store
        self.session_factory = session_factory
        self.cipher = cipher
        self.redis = redis
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.retry_delay_seconds = retry_delay_seconds

    async def _tenant_slug(
        self,
        claimed: ClaimedOutboxMessage,
    ) -> str:
        """Resolve the active tenant for authenticated decryption."""

        async with self.session_factory() as session:
            slug = await session.scalar(
                select(Organization.slug).where(
                    Organization.id == claimed.organization_id,
                    Organization.is_active.is_(True),
                )
            )

        if not slug:
            raise ValueError("Outbox tenant unavailable")

        return slug

    async def dispatch_once(self) -> str:
        """Perform one outbox publication attempt.

        Returns:
            idle       - no eligible record
            published  - Redis accepted the message and
                         PostgreSQL acknowledged publication
            retrying   - a publication error was recorded

        A Redis publication followed by an acknowledgement failure
        can lead to repeated delivery. Consumers must deduplicate.
        """

        claimed = await self.dispatch_store.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )

        if claimed is None:
            return "idle"

        try:
            tenant_id = await self._tenant_slug(claimed)

            job = self.cipher.decrypt(
                claimed.payload_ciphertext,
                claimed.encryption_key_id,
                tenant_id=tenant_id,
                job_id=claimed.job_id,
            )

            await enqueue(self.redis, job)

        except Exception as exc:
            # Store only a safe classification, never raw exception
            # text or decrypted customer payload data.
            if isinstance(exc, JobEncryptionError):
                error_code = "invalid_envelope"
            elif isinstance(exc, (ValueError, KeyError)):
                error_code = "invalid_envelope"
            else:
                error_code = "publish_error"

            recorded = await self.dispatch_store.mark_failed(
                claimed.organization_id,
                claimed.job_id,
                self.worker_id,
                claimed.lease_token,
                retry_delay_seconds=self.retry_delay_seconds,
                error_code=error_code,
            )

            if not recorded:
                raise RuntimeError(
                    "Outbox publication failure could not be recorded"
                ) from exc

            return "retrying"

        acknowledged = await self.dispatch_store.mark_published(
            claimed.organization_id,
            claimed.job_id,
            self.worker_id,
            claimed.lease_token,
        )

        if not acknowledged:
            raise RuntimeError(
                "Redis publication succeeded but PostgreSQL "
                "acknowledgement was rejected; duplicate delivery "
                "is possible"
            )

        return "published"
