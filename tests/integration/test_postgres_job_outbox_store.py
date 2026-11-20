"""Integration tests for encrypted transactional job publishing.

Requires:
    RUN_INTEGRATION_TESTS=1
    PostgreSQL migration 0005

Uses fictional jobs and cleans up test records.
No Redis messages or external requests are generated.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from apps.worker.jobs.envelope import JobEnvelope
from core.config.settings import Settings
from core.security.job_encryption import JobEnvelopeCipher
from database.models.background_job import BackgroundJob
from database.models.job_outbox import JobOutbox
from database.repositories.postgres_job_outbox_store import (
    PostgresJobOutboxStore,
)
from database.sessions.engine import (
    create_engine,
    create_session_factory,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL integration tests are disabled",
    ),
]


@pytest.fixture
async def publisher_setup():
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
    created_ids: list[str] = []

    try:
        yield publisher, factory, cipher, created_ids

    finally:
        try:
            if created_ids:
                async with factory() as session, session.begin():
                    # Delete child records before parent records.
                    await session.execute(
                        delete(JobOutbox).where(JobOutbox.job_id.in_(created_ids))
                    )
                    await session.execute(
                        delete(BackgroundJob).where(BackgroundJob.job_id.in_(created_ids))
                    )
        finally:
            await engine.dispose()


def make_job(
    created_ids: list[str],
    *,
    tenant_id: str = "demo-org",
) -> JobEnvelope:
    job_id = "test-" + uuid.uuid4().hex
    created_ids.append(job_id)

    return JobEnvelope(
        job_id=job_id,
        tenant_id=tenant_id,
        job_type="knowledge.ingest",
        payload={
            "document_id": "fictional-document",
            "message": "Confidential fictional customer content",
        },
        max_attempts=3,
    )


async def load_records(factory, job_id):
    async with factory() as session:
        job = await session.scalar(select(BackgroundJob).where(BackgroundJob.job_id == job_id))

        outbox = await session.scalar(select(JobOutbox).where(JobOutbox.job_id == job_id))

        return job, outbox


async def test_publish_creates_both_records(publisher_setup):
    publisher, factory, _, created_ids = publisher_setup
    job = make_job(created_ids)

    result = await publisher.publish(job)

    assert result == job.job_id

    saved_job, outbox = await load_records(factory, job.job_id)

    assert saved_job is not None
    assert outbox is not None

    assert saved_job.job_type == job.job_type
    assert saved_job.status == "pending"
    assert saved_job.attempts == 0
    assert saved_job.max_attempts == 3

    assert outbox.status == "pending"
    assert outbox.publish_attempts == 0

    assert outbox.organization_id == saved_job.organization_id


async def test_payload_is_encrypted_at_rest(publisher_setup):
    publisher, factory, cipher, created_ids = publisher_setup
    job = make_job(created_ids)

    await publisher.publish(job)

    _, outbox = await load_records(factory, job.job_id)

    assert outbox is not None
    assert isinstance(outbox.payload_ciphertext, bytes)

    assert b"Confidential fictional customer content" not in outbox.payload_ciphertext

    restored = cipher.decrypt(
        outbox.payload_ciphertext,
        outbox.encryption_key_id,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
    )

    assert restored == job


async def test_identical_publish_is_idempotent(publisher_setup):
    publisher, factory, _, created_ids = publisher_setup
    job = make_job(created_ids)

    await publisher.publish(job)

    original_job, original_outbox = await load_records(factory, job.job_id)

    assert original_job is not None
    assert original_outbox is not None

    await publisher.publish(job)

    saved_job, saved_outbox = await load_records(factory, job.job_id)

    assert saved_job.id == original_job.id
    assert saved_outbox.id == original_outbox.id

    assert saved_outbox.payload_ciphertext == original_outbox.payload_ciphertext


async def test_conflicting_payload_is_rejected(publisher_setup):
    publisher, factory, _, created_ids = publisher_setup
    job = make_job(created_ids)

    await publisher.publish(job)

    conflicting = job.model_copy(update={"payload": {"document_id": "different-document"}})

    with pytest.raises(
        ValueError,
        match="Conflicting job payload",
    ):
        await publisher.publish(conflicting)

    _, outbox = await load_records(factory, job.job_id)

    assert outbox is not None


async def test_unknown_tenant_creates_no_records(publisher_setup):
    publisher, factory, _, created_ids = publisher_setup

    job = make_job(
        created_ids,
        tenant_id="nonexistent-test-tenant",
    )

    with pytest.raises(
        ValueError,
        match="Unknown or inactive organization",
    ):
        await publisher.publish(job)

    saved_job, outbox = await load_records(factory, job.job_id)

    assert saved_job is None
    assert outbox is None


async def test_transaction_rolls_back_on_error(publisher_setup):
    publisher, factory, cipher, created_ids = publisher_setup
    job = make_job(created_ids)

    # Simulate a failure after the INSERT statements but
    # before the surrounding PostgreSQL transaction commits.
    with (
        patch.object(
            cipher,
            "decrypt",
            side_effect=RuntimeError("Fictional validation failure"),
        ),
        pytest.raises(
            RuntimeError,
            match="Fictional validation failure",
        ),
    ):
        await publisher.publish(job)

    saved_job, outbox = await load_records(factory, job.job_id)

    assert saved_job is None
    assert outbox is None


async def test_concurrent_identical_publication(publisher_setup):
    import asyncio

    publisher, factory, _, created_ids = publisher_setup
    job = make_job(created_ids)

    results = await asyncio.gather(
        publisher.publish(job),
        publisher.publish(job),
    )

    assert results == [job.job_id, job.job_id]

    saved_job, outbox = await load_records(factory, job.job_id)

    assert saved_job is not None
    assert outbox is not None
