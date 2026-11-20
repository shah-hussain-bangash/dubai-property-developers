"""Integration tests for background-job recovery claim protection.

Requires PostgreSQL migration 0006 and RUN_INTEGRATION_TESTS=1.

Uses fictional jobs and cleans up its test records.
Does not access Redis or change running Docker workers.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

from core.config.settings import Settings
from database.models.background_job import BackgroundJob
from database.models.job_recovery_operation import (
    JobRecoveryOperation,
)
from database.repositories.postgres_background_job_store import (
    PostgresBackgroundJobStore,
)
from database.repositories.postgres_job_recovery_operation_store import (
    PostgresJobRecoveryOperationStore,
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
async def recovery_guard_setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    jobs = PostgresBackgroundJobStore(factory)
    recovery = PostgresJobRecoveryOperationStore(factory)
    created_ids = []

    try:
        yield jobs, recovery, factory, created_ids

    finally:
        try:
            if created_ids:
                async with factory() as session, session.begin():
                    await session.execute(
                        delete(JobRecoveryOperation).where(
                            JobRecoveryOperation.job_id.in_(created_ids)
                        )
                    )
                    await session.execute(
                        delete(BackgroundJob).where(BackgroundJob.job_id.in_(created_ids))
                    )
        finally:
            await engine.dispose()


async def create_recoverable_job(
    jobs,
    recovery,
    factory,
    created_ids,
):
    """Create a fictional job with a pending recovery operation."""

    job_id = "test-claim-guard-" + uuid.uuid4().hex
    created_ids.append(job_id)

    record = await jobs.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
        max_attempts=3,
    )

    token = await jobs.claim(
        "demo-org",
        job_id,
        "original-worker",
    )
    assert token is not None

    async with factory() as session, session.begin():
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == record.id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    operation_id = await recovery.begin_expired_recovery(
        "demo-org",
        job_id,
        retry_delay_seconds=0,
    )

    assert operation_id is not None

    return job_id, operation_id


async def set_operation_status(
    factory,
    operation_id,
    status,
):
    """Change only this fictional recovery operation's status."""

    async with factory() as session, session.begin():
        await session.execute(
            update(JobRecoveryOperation)
            .where(JobRecoveryOperation.id == operation_id)
            .values(status=status)
        )


async def get_job(jobs, job_id):
    return await jobs.get("demo-org", job_id)


@pytest.mark.parametrize(
    "recovery_status",
    ["pending", "processing", "retrying"],
)
async def test_unresolved_recovery_blocks_claim(
    recovery_guard_setup,
    recovery_status,
):
    jobs, recovery, factory, ids = recovery_guard_setup

    job_id, operation_id = await create_recoverable_job(
        jobs,
        recovery,
        factory,
        ids,
    )

    await set_operation_status(
        factory,
        operation_id,
        recovery_status,
    )

    token = await jobs.claim(
        "demo-org",
        job_id,
        "new-worker",
    )

    assert token is None

    saved = await get_job(jobs, job_id)

    assert saved.status == "retrying"
    assert saved.attempts == 1
    assert saved.worker_id is None
    assert saved.lease_token is None


async def test_completed_recovery_allows_claim(
    recovery_guard_setup,
):
    jobs, recovery, factory, ids = recovery_guard_setup

    job_id, operation_id = await create_recoverable_job(
        jobs,
        recovery,
        factory,
        ids,
    )

    await set_operation_status(
        factory,
        operation_id,
        "completed",
    )

    token = await jobs.claim(
        "demo-org",
        job_id,
        "new-worker",
    )

    assert token is not None

    saved = await get_job(jobs, job_id)

    assert saved.status == "processing"
    assert saved.worker_id == "new-worker"
    assert saved.lease_token == token
    assert saved.attempts == 2


async def test_unrelated_job_is_not_blocked(
    recovery_guard_setup,
):
    jobs, recovery, factory, ids = recovery_guard_setup

    blocked_job_id, _ = await create_recoverable_job(
        jobs,
        recovery,
        factory,
        ids,
    )

    other_job_id = "test-claim-guard-" + uuid.uuid4().hex
    ids.append(other_job_id)

    await jobs.register(
        "demo-org",
        other_job_id,
        "knowledge.ingest",
    )

    blocked_token = await jobs.claim(
        "demo-org",
        blocked_job_id,
        "new-worker",
    )

    other_token = await jobs.claim(
        "demo-org",
        other_job_id,
        "new-worker",
    )

    assert blocked_token is None
    assert other_token is not None

    saved = await get_job(jobs, other_job_id)

    assert saved.status == "processing"
    assert saved.attempts == 1


async def test_all_unresolved_attempts_must_finish(
    recovery_guard_setup,
):
    """One completed operation cannot hide another unresolved one."""

    jobs, recovery, factory, ids = recovery_guard_setup

    job_id, operation_id = await create_recoverable_job(
        jobs,
        recovery,
        factory,
        ids,
    )

    async with factory() as session, session.begin():
        original = await session.scalar(
            select(JobRecoveryOperation).where(JobRecoveryOperation.id == operation_id)
        )

        assert original is not None
        original.status = "completed"

        session.add(
            JobRecoveryOperation(
                id=uuid.uuid4(),
                organization_id=original.organization_id,
                job_id=job_id,
                job_attempt=2,
                status="pending",
                attempts=0,
            )
        )

    token = await jobs.claim(
        "demo-org",
        job_id,
        "new-worker",
    )

    assert token is None

    saved = await get_job(jobs, job_id)
    assert saved.attempts == 1
    assert saved.status == "retrying"
