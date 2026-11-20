"""Integration tests for PostgreSQL expired-lease recovery.

Uses fictional background jobs and removes their records.
Does not read or modify Redis queues.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update

from core.config.settings import Settings
from database.models.background_job import BackgroundJob
from database.repositories.postgres_background_job_store import (
    PostgresBackgroundJobStore,
)
from database.repositories.postgres_job_recovery_store import (
    PostgresJobRecoveryStore,
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
async def recovery_setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    job_store = PostgresBackgroundJobStore(factory)
    recovery_store = PostgresJobRecoveryStore(factory)

    created_ids: list[str] = []

    try:
        yield job_store, recovery_store, factory, created_ids
    finally:
        try:
            if created_ids:
                async with factory() as session, session.begin():
                    await session.execute(
                        delete(BackgroundJob).where(BackgroundJob.job_id.in_(created_ids))
                    )
        finally:
            await engine.dispose()


async def create_job(
    job_store,
    created_ids,
    *,
    max_attempts=3,
):
    job_id = "test-recovery-" + uuid.uuid4().hex
    created_ids.append(job_id)

    record = await job_store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
        max_attempts=max_attempts,
    )

    return job_id, record


async def expire_lease(factory, record_id):
    async with factory() as session, session.begin():
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == record_id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )


async def test_expired_lease_becomes_retrying(recovery_setup):
    job_store, recovery, factory, ids = recovery_setup

    job_id, record = await create_job(job_store, ids)

    token = await job_store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    await expire_lease(factory, record.id)

    outcome = await recovery.recover_expired_lease(
        "demo-org",
        job_id,
        retry_delay_seconds=60,
    )

    assert outcome == "retrying"

    saved = await job_store.get("demo-org", job_id)

    assert saved.status == "retrying"
    assert saved.worker_id is None
    assert saved.lease_token is None
    assert saved.lease_expires_at is None
    assert saved.next_retry_at is not None
    assert saved.attempts == 1

    # Original worker can no longer complete the job.
    assert (
        await job_store.complete(
            "demo-org",
            job_id,
            "worker-A",
            token,
        )
        is False
    )

    # Scheduled retry cannot be claimed prematurely.
    assert (
        await job_store.claim(
            "demo-org",
            job_id,
            "worker-B",
        )
        is None
    )


async def test_active_lease_cannot_be_recovered(recovery_setup):
    job_store, recovery, _, ids = recovery_setup

    job_id, _ = await create_job(job_store, ids)

    token = await job_store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    outcome = await recovery.recover_expired_lease(
        "demo-org",
        job_id,
    )

    assert outcome is None

    saved = await job_store.get("demo-org", job_id)

    assert saved.status == "processing"
    assert saved.lease_token == token


async def test_exhausted_job_becomes_failed(recovery_setup):
    job_store, recovery, factory, ids = recovery_setup

    job_id, record = await create_job(
        job_store,
        ids,
        max_attempts=1,
    )

    token = await job_store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    await expire_lease(factory, record.id)

    outcome = await recovery.recover_expired_lease(
        "demo-org",
        job_id,
    )

    assert outcome == "failed"

    saved = await job_store.get("demo-org", job_id)

    assert saved.status == "failed"
    assert saved.finished_at is not None
    assert saved.next_retry_at is None
    assert saved.error_code == "timeout"


async def test_only_one_recovery_wins(recovery_setup):
    job_store, recovery, factory, ids = recovery_setup

    job_id, record = await create_job(job_store, ids)

    token = await job_store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    await expire_lease(factory, record.id)

    outcomes = await asyncio.gather(
        recovery.recover_expired_lease(
            "demo-org",
            job_id,
        ),
        recovery.recover_expired_lease(
            "demo-org",
            job_id,
        ),
    )

    assert outcomes.count("retrying") == 1
    assert outcomes.count(None) == 1


async def test_missing_registration_is_not_recovered(
    recovery_setup,
):
    _, recovery, _, _ = recovery_setup

    outcome = await recovery.recover_expired_lease(
        "demo-org",
        "missing-" + uuid.uuid4().hex,
    )

    assert outcome is None


async def test_wrong_tenant_cannot_recover_job(
    recovery_setup,
):
    job_store, recovery, factory, ids = recovery_setup

    job_id, record = await create_job(job_store, ids)

    token = await job_store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    await expire_lease(factory, record.id)

    # A different tenant must not recover demo-org's job.
    # If the tenant does not exist, the outcome is still None.
    outcome = await recovery.recover_expired_lease(
        "tenant-isolation-test",
        job_id,
    )

    assert outcome is None

    saved = await job_store.get("demo-org", job_id)

    assert saved.status == "processing"
