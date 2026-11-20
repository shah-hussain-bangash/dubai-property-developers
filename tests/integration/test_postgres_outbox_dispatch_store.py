"""PostgreSQL integration tests for outbox dispatcher claims.

Requires:
    RUN_INTEGRATION_TESTS=1
    Development PostgreSQL with migration 0005 applied.

Uses fictional encrypted jobs and removes test records.
Does not connect to Redis or execute job handlers.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update

from apps.worker.jobs.envelope import JobEnvelope
from core.config.settings import Settings
from core.security.job_encryption import JobEnvelopeCipher
from database.models.background_job import BackgroundJob
from database.models.job_outbox import JobOutbox
from database.repositories.postgres_job_outbox_store import (
    PostgresJobOutboxStore,
)
from database.repositories.postgres_outbox_dispatch_store import (
    PostgresOutboxDispatchStore,
)
from database.sessions.engine import (
    create_engine,
    create_session_factory,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL integration tests disabled",
    ),
]


@pytest.fixture
async def dispatch_setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    cipher = JobEnvelopeCipher(
        keys={"test-key": os.urandom(32)},
        active_key_id="test-key",
    )

    publisher = PostgresJobOutboxStore(factory, cipher)
    dispatch = PostgresOutboxDispatchStore(factory)

    created_ids: list[str] = []

    try:
        yield publisher, dispatch, factory, cipher, created_ids
    finally:
        try:
            if created_ids:
                async with factory() as session, session.begin():
                    await session.execute(
                        delete(JobOutbox).where(JobOutbox.job_id.in_(created_ids))
                    )
                    await session.execute(
                        delete(BackgroundJob).where(BackgroundJob.job_id.in_(created_ids))
                    )
        finally:
            await engine.dispose()


async def make_message(publisher, created_ids):
    job_id = "test-" + uuid.uuid4().hex
    created_ids.append(job_id)

    job = JobEnvelope(
        job_id=job_id,
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={
            "document_id": "fictional-document",
        },
    )

    await publisher.publish(job)
    return job


async def claim_expected(dispatch, job_id, worker_id):
    """Claim the fictional job.

    These tests assume an idle development outbox. If another
    eligible message exists, fail clearly rather than changing
    unrelated publication records intentionally.
    """

    claimed = await dispatch.claim_next(worker_id)

    assert claimed is not None, "No eligible outbox message"
    assert claimed.job_id == job_id, (
        "An unrelated pending outbox record was claimed. "
        "Run these tests against an idle, isolated development database."
    )

    return claimed


async def test_claim_and_decrypt_message(dispatch_setup):
    publisher, dispatch, _, cipher, ids = dispatch_setup

    job = await make_message(publisher, ids)

    claimed = await claim_expected(dispatch, job.job_id, "dispatcher-A")

    assert claimed.publish_attempts == 1
    assert claimed.lease_token

    restored = cipher.decrypt(
        claimed.payload_ciphertext,
        claimed.encryption_key_id,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
    )

    assert restored == job


async def test_concurrent_claim_is_exclusive(dispatch_setup):
    publisher, dispatch, _, _, ids = dispatch_setup

    job = await make_message(publisher, ids)

    claims = await asyncio.gather(
        dispatch.claim_next("dispatcher-A"),
        dispatch.claim_next("dispatcher-B"),
    )

    matches = [claim for claim in claims if claim is not None and claim.job_id == job.job_id]

    assert len(matches) == 1


async def test_renewal_requires_correct_owner(dispatch_setup):
    publisher, dispatch, _, _, ids = dispatch_setup

    job = await make_message(publisher, ids)
    claimed = await claim_expected(dispatch, job.job_id, "dispatcher-A")

    wrong = await dispatch.renew_lease(
        claimed.organization_id,
        job.job_id,
        "dispatcher-B",
        claimed.lease_token,
    )

    assert wrong is False

    correct = await dispatch.renew_lease(
        claimed.organization_id,
        job.job_id,
        "dispatcher-A",
        claimed.lease_token,
    )

    assert correct is True


async def test_mark_published_rejects_stale_owner(dispatch_setup):
    publisher, dispatch, _, _, ids = dispatch_setup

    job = await make_message(publisher, ids)
    claimed = await claim_expected(dispatch, job.job_id, "dispatcher-A")

    wrong = await dispatch.mark_published(
        claimed.organization_id,
        job.job_id,
        "dispatcher-B",
        claimed.lease_token,
    )

    assert wrong is False

    success = await dispatch.mark_published(
        claimed.organization_id,
        job.job_id,
        "dispatcher-A",
        claimed.lease_token,
    )

    assert success is True

    # Published messages are no longer eligible for claims.
    another = await dispatch.claim_next("dispatcher-C")
    assert another is None or another.job_id != job.job_id


async def test_failure_schedules_retry(dispatch_setup):
    publisher, dispatch, factory, _, ids = dispatch_setup

    job = await make_message(publisher, ids)
    claimed = await claim_expected(dispatch, job.job_id, "dispatcher-A")

    failed = await dispatch.mark_failed(
        claimed.organization_id,
        job.job_id,
        "dispatcher-A",
        claimed.lease_token,
        retry_delay_seconds=3600,
        error_code="redis_unavailable",
    )

    assert failed is True

    async with factory() as session:
        record = await session.get(
            JobOutbox,
            # Look up by business job ID below instead of UUID.
            uuid.uuid4(),
        )
        assert record is None

        from sqlalchemy import select

        record = await session.scalar(select(JobOutbox).where(JobOutbox.job_id == job.job_id))

        assert record is not None
        assert record.status == "retrying"
        assert record.next_attempt_at is not None
        assert record.error_code == "redis_unavailable"

    another = await dispatch.claim_next("dispatcher-B")

    assert another is None or another.job_id != job.job_id


async def test_expired_claim_can_be_recovered(dispatch_setup):
    publisher, dispatch, factory, _, ids = dispatch_setup

    job = await make_message(publisher, ids)

    original = await claim_expected(dispatch, job.job_id, "dispatcher-A")

    # Expire only the fictional test publication.
    async with factory() as session, session.begin():
        await session.execute(
            update(JobOutbox)
            .where(
                JobOutbox.organization_id == original.organization_id,
                JobOutbox.job_id == job.job_id,
            )
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    recovered = await claim_expected(dispatch, job.job_id, "dispatcher-B")

    assert recovered.lease_token != original.lease_token
    assert recovered.publish_attempts == 2

    stale_ack = await dispatch.mark_published(
        original.organization_id,
        job.job_id,
        "dispatcher-A",
        original.lease_token,
    )

    assert stale_ack is False

    valid_ack = await dispatch.mark_published(
        recovered.organization_id,
        job.job_id,
        "dispatcher-B",
        recovered.lease_token,
    )

    assert valid_ack is True
