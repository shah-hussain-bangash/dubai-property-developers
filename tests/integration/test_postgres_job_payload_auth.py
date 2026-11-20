"""Integration tests for Redis job-envelope authentication.

Requires:
    RUN_INTEGRATION_TESTS=1
    PostgreSQL with migration 0005 applied.

Uses fictional jobs, temporary encryption keys, and automatic
cleanup. Does not publish to Redis or execute job handlers.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, select, update

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.payload_auth import (
    JobPayloadAuthenticationError,
    PostgresJobPayloadAuthenticator,
)
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
async def auth_setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    cipher = JobEnvelopeCipher(
        keys={"test-auth-key": os.urandom(32)},
        active_key_id="test-auth-key",
    )

    publisher = PostgresJobOutboxStore(factory, cipher)
    authenticator = PostgresJobPayloadAuthenticator(
        factory,
        cipher,
    )

    created_ids: list[str] = []

    try:
        yield publisher, authenticator, factory, created_ids

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


async def create_test_job(publisher, created_ids):
    job = JobEnvelope(
        job_id="test-" + uuid.uuid4().hex,
        tenant_id="demo-org",
        job_type="knowledge.ingest",
        payload={
            "document_id": "fictional-document",
            "message": "Fictional private content",
        },
        max_attempts=3,
    )

    created_ids.append(job.job_id)
    await publisher.publish(job)

    return job


async def test_original_job_is_authenticated(auth_setup):
    publisher, authenticator, _, ids = auth_setup

    job = await create_test_job(publisher, ids)

    authenticated = await authenticator.authenticate(job)

    assert authenticated == job


async def test_modified_payload_is_rejected(auth_setup):
    publisher, authenticator, _, ids = auth_setup

    job = await create_test_job(publisher, ids)

    modified = job.model_copy(
        update={
            "payload": {
                "document_id": "unauthorized-document",
            }
        }
    )

    with pytest.raises(
        JobPayloadAuthenticationError,
        match="differs from authenticated publication",
    ):
        await authenticator.authenticate(modified)


async def test_forged_job_id_is_rejected(auth_setup):
    publisher, authenticator, _, ids = auth_setup

    job = await create_test_job(publisher, ids)

    forged = job.model_copy(update={"job_id": "forged-" + uuid.uuid4().hex})

    with pytest.raises(
        JobPayloadAuthenticationError,
        match="not found",
    ):
        await authenticator.authenticate(forged)


async def test_incorrect_tenant_is_rejected(auth_setup):
    publisher, authenticator, _, ids = auth_setup

    job = await create_test_job(publisher, ids)

    wrong_tenant = job.model_copy(update={"tenant_id": "another-tenant"})

    with pytest.raises(
        JobPayloadAuthenticationError,
        match="not found",
    ):
        await authenticator.authenticate(wrong_tenant)


async def test_modified_job_type_is_rejected(auth_setup):
    publisher, authenticator, _, ids = auth_setup

    job = await create_test_job(publisher, ids)

    modified = job.model_copy(update={"job_type": "followup.scan"})

    with pytest.raises(
        JobPayloadAuthenticationError,
        match="differs from authenticated publication",
    ):
        await authenticator.authenticate(modified)


async def test_tampered_stored_ciphertext_is_rejected(auth_setup):
    publisher, authenticator, factory, ids = auth_setup

    job = await create_test_job(publisher, ids)

    async with factory() as session:
        original = await session.scalar(
            select(JobOutbox.payload_ciphertext).where(JobOutbox.job_id == job.job_id)
        )

    assert original is not None

    tampered = bytearray(original)
    tampered[-1] ^= 1

    # Change only this fictional test record.
    async with factory() as session, session.begin():
        await session.execute(
            update(JobOutbox)
            .where(JobOutbox.job_id == job.job_id)
            .values(payload_ciphertext=bytes(tampered))
        )

    with pytest.raises(
        JobPayloadAuthenticationError,
        match="authentication failed",
    ):
        await authenticator.authenticate(job)
