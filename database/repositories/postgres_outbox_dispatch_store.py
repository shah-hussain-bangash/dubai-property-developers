
"""PostgreSQL outbox dispatcher state management.

Supports exclusive publication claims, expired claim recovery,
lease-protected acknowledgements, and scheduled retries.

This repository does not decrypt envelopes or publish to Redis.
Those operations belong to the dispatcher service.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.job_outbox import JobOutbox


@dataclass(frozen=True)
class ClaimedOutboxMessage:
    """Immutable publication claim returned to a dispatcher."""

    organization_id: uuid.UUID
    job_id: str
    payload_ciphertext: bytes
    encryption_key_id: str
    lease_token: str
    publish_attempts: int


class PostgresOutboxDispatchStore:
    """Manage outbox publication ownership in PostgreSQL."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _validate_owner(
        worker_id: str,
        lease_token: str | None = None,
    ) -> None:
        if (
            not isinstance(worker_id, str)
            or not worker_id.strip()
            or len(worker_id) > 128
        ):
            raise ValueError("Invalid dispatcher worker_id")

        if lease_token is not None and (
            not isinstance(lease_token, str)
            or not lease_token
            or len(lease_token) > 64
        ):
            raise ValueError("Invalid dispatcher lease_token")

    async def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int = 120,
    ) -> ClaimedOutboxMessage | None:
        """Claim one eligible publication without blocking other workers.

        Eligible records:
        - Pending publications whose retry time has elapsed.
        - Retry publications whose retry time has elapsed.
        - Publishing records whose dispatcher lease has expired.

        SKIP LOCKED prevents concurrent dispatchers from claiming
        the same row.
        """

        self._validate_owner(worker_id)

        if not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")

        now = datetime.now(UTC)
        lease_token = uuid.uuid4().hex

        async with self.session_factory() as session:
            async with session.begin():
                record = await session.scalar(
                    select(JobOutbox)
                    .where(
                        or_(
                            (
                                JobOutbox.status.in_(
                                    ["pending", "retrying"]
                                )
                                & or_(
                                    JobOutbox.next_attempt_at.is_(None),
                                    JobOutbox.next_attempt_at <= now,
                                )
                            ),
                            (
                                (JobOutbox.status == "publishing")
                                & JobOutbox.lease_expires_at.is_not(None)
                                & (JobOutbox.lease_expires_at <= now)
                            ),
                        )
                    )
                    .order_by(
                        JobOutbox.created_at,
                        JobOutbox.id,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )

                if record is None:
                    return None

                record.status = "publishing"
                record.worker_id = worker_id
                record.lease_token = lease_token
                record.lease_expires_at = (
                    now + timedelta(seconds=lease_seconds)
                )
                record.next_attempt_at = None
                record.publish_attempts += 1
                record.error_code = None

                await session.flush()

                return ClaimedOutboxMessage(
                    organization_id=record.organization_id,
                    job_id=record.job_id,
                    payload_ciphertext=bytes(
                        record.payload_ciphertext
                    ),
                    encryption_key_id=record.encryption_key_id,
                    lease_token=lease_token,
                    publish_attempts=record.publish_attempts,
                )

    async def renew_lease(
        self,
        organization_id: uuid.UUID,
        job_id: str,
        worker_id: str,
        lease_token: str,
        *,
        lease_seconds: int = 120,
    ) -> bool:
        """Extend a publication claim owned by this dispatcher."""

        self._validate_owner(worker_id, lease_token)

        if not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")

        now = datetime.now(UTC)

        async with self.session_factory() as session:
            async with session.begin():
                result = await session.scalar(
                    update(JobOutbox)
                    .where(
                        JobOutbox.organization_id == organization_id,
                        JobOutbox.job_id == job_id,
                        JobOutbox.status == "publishing",
                        JobOutbox.worker_id == worker_id,
                        JobOutbox.lease_token == lease_token,
                        JobOutbox.lease_expires_at > now,
                    )
                    .values(
                        lease_expires_at=now
                        + timedelta(seconds=lease_seconds)
                    )
                    .returning(JobOutbox.id)
                )

                return result is not None

    async def mark_published(
        self,
        organization_id: uuid.UUID,
        job_id: str,
        worker_id: str,
        lease_token: str,
    ) -> bool:
        """Acknowledge a publication under its current lease."""

        self._validate_owner(worker_id, lease_token)

        now = datetime.now(UTC)

        async with self.session_factory() as session:
            async with session.begin():
                result = await session.scalar(
                    update(JobOutbox)
                    .where(
                        JobOutbox.organization_id == organization_id,
                        JobOutbox.job_id == job_id,
                        JobOutbox.status == "publishing",
                        JobOutbox.worker_id == worker_id,
                        JobOutbox.lease_token == lease_token,
                        JobOutbox.lease_expires_at > now,
                    )
                    .values(
                        status="published",
                        worker_id=None,
                        lease_token=None,
                        lease_expires_at=None,
                        next_attempt_at=None,
                        published_at=now,
                        error_code=None,
                    )
                    .returning(JobOutbox.id)
                )

                return result is not None

    async def mark_failed(
        self,
        organization_id: uuid.UUID,
        job_id: str,
        worker_id: str,
        lease_token: str,
        *,
        retry_delay_seconds: int = 30,
        error_code: str = "publish_error",
    ) -> bool:
        """Release the current claim and schedule another attempt."""

        self._validate_owner(worker_id, lease_token)

        if (
            not isinstance(retry_delay_seconds, int)
            or retry_delay_seconds < 0
        ):
            raise ValueError("retry_delay_seconds must be >= 0")

        allowed_error_codes = {
            "publish_error",
            "redis_unavailable",
            "encryption_key_unavailable",
            "invalid_envelope",
        }

        if error_code not in allowed_error_codes:
            error_code = "publish_error"

        now = datetime.now(UTC)

        async with self.session_factory() as session:
            async with session.begin():
                result = await session.scalar(
                    update(JobOutbox)
                    .where(
                        JobOutbox.organization_id == organization_id,
                        JobOutbox.job_id == job_id,
                        JobOutbox.status == "publishing",
                        JobOutbox.worker_id == worker_id,
                        JobOutbox.lease_token == lease_token,
                        JobOutbox.lease_expires_at > now,
                    )
                    .values(
                        status="retrying",
                        worker_id=None,
                        lease_token=None,
                        lease_expires_at=None,
                        next_attempt_at=now
                        + timedelta(seconds=retry_delay_seconds),
                        error_code=error_code,
                    )
                    .returning(JobOutbox.id)
                )

                return result is not None
