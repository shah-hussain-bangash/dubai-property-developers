
"""Integration tests for transactional job recovery registration.

Requires RUN_INTEGRATION_TESTS=1 and PostgreSQL migration 0006.

All test jobs are fictional. The fixture removes recovery records
before their parent background jobs. Redis is never accessed.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from core.config.settings import Settings
from database.models.background_job import BackgroundJob
from database.models.job_recovery_operation import JobRecoveryOperation
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
async def recovery_setup():
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
                async with factory() as session:
                    async with session.begin():
                        await session.execute(
                            delete(JobRecoveryOperation).where(
                                JobRecoveryOperation.job_id.in_(
                                    created_ids
                                )
                            )
                        )
                        await session.execute(
                            delete(BackgroundJob).where(
                                BackgroundJob.job_id.in_(
                                    created_ids
                                )
                            )
                        )
        finally:
            await engine.dispose()


async def create_job(
    jobs,
    created_ids,
    *,
    max_attempts=3,
):
    job_id = "test-recovery-op-" + uuid.uuid4().hex
    created_ids.append(job_id)

    record = await jobs.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
        max_attempts=max_attempts,
    )

    token = await jobs.claim(
        "demo-org",
        job_id,
        "fictional-worker-A",
    )

    assert token is not None

    return job_id, record, token


async def expire_job(factory, record_id):
    async with factory() as session:
        async with session.begin():
            await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.id == record_id)
                .values(
                    lease_expires_at=(
                        datetime.now(UTC)
                        - timedelta(minutes=5)
                    )
                )
            )


async def find_operations(factory, job_id):
    async with factory() as session:
        result = await session.scalars(
            select(JobRecoveryOperation).where(
                JobRecoveryOperation.job_id == job_id
            )
        )
        return list(result.all())


async def test_expired_job_and_operation_commit_together(
    recovery_setup,
):
    jobs, recovery, factory, ids = recovery_setup

    job_id, record, token = await create_job(jobs, ids)
    await expire_job(factory, record.id)

    operation_id = await recovery.begin_expired_recovery(
        "demo-org",
        job_id,
        retry_delay_seconds=60,
    )

    assert operation_id is not None

    saved = await jobs.get("demo-org", job_id)
    operations = await find_operations(factory, job_id)

    assert saved.status == "retrying"
    assert saved.worker_id is None
    assert saved.lease_token is None
    assert saved.lease_expires_at is None
    assert saved.next_retry_at is not None
    assert saved.attempts == 1

    assert len(operations) == 1
    assert operations[0].id == operation_id
    assert operations[0].job_attempt == 1
    assert operations[0].status == "pending"
    assert operations[0].attempts == 0

    # The previous owner cannot complete its expired attempt.
    assert await jobs.complete(
        "demo-org",
        job_id,
        "fictional-worker-A",
        token,
    ) is False


async def test_active_lease_is_not_recovered(recovery_setup):
    jobs, recovery, factory, ids = recovery_setup

    job_id, _, token = await create_job(jobs, ids)

    operation_id = await recovery.begin_expired_recovery(
        "demo-org",
        job_id,
    )

    assert operation_id is None
    assert await find_operations(factory, job_id) == []

    saved = await jobs.get("demo-org", job_id)
    assert saved.status == "processing"
    assert saved.lease_token == token


async def test_exhausted_attempt_creates_terminal_recovery(
    recovery_setup,
):
    jobs, recovery, factory, ids = recovery_setup

    job_id, record, _ = await create_job(
        jobs,
        ids,
        max_attempts=1,
    )
    await expire_job(factory, record.id)

    operation_id = await recovery.begin_expired_recovery(
        "demo-org",
        job_id,
    )

    assert operation_id is not None

    saved = await jobs.get("demo-org", job_id)
    operations = await find_operations(factory, job_id)

    assert saved.status == "failed"
    assert saved.finished_at is not None
    assert saved.next_retry_at is None
    assert saved.error_code == "timeout"

    assert len(operations) == 1
    assert operations[0].job_attempt == 1
    assert operations[0].status == "pending"


async def test_only_one_concurrent_recovery_succeeds(
    recovery_setup,
):
    jobs, recovery, factory, ids = recovery_setup

    job_id, record, _ = await create_job(jobs, ids)
    await expire_job(factory, record.id)

    results = await asyncio.gather(
        recovery.begin_expired_recovery(
            "demo-org",
            job_id,
        ),
        recovery.begin_expired_recovery(
            "demo-org",
            job_id,
        ),
    )

    assert sum(value is not None for value in results) == 1

    operations = await find_operations(factory, job_id)
    assert len(operations) == 1


async def test_wrong_tenant_cannot_register_recovery(
    recovery_setup,
):
    jobs, recovery, factory, ids = recovery_setup

    job_id, record, _ = await create_job(jobs, ids)
    await expire_job(factory, record.id)

    result = await recovery.begin_expired_recovery(
        "tenant-isolation-test",
        job_id,
    )

    assert result is None
    assert await find_operations(factory, job_id) == []

    saved = await jobs.get("demo-org", job_id)
    assert saved.status == "processing"


async def test_constraint_error_rolls_back_job_transition(
    recovery_setup,
):
    jobs, recovery, factory, ids = recovery_setup

    job_id, record, token = await create_job(jobs, ids)
    await expire_job(factory, record.id)

    # Deliberately create an operation for this attempt.
    # The next recovery will violate the unique constraint.
    # Its background-job update must be rolled back too.
    async with factory() as session:
        async with session.begin():
            session.add(
                JobRecoveryOperation(
                    id=uuid.uuid4(),
                    organization_id=record.organization_id,
                    job_id=job_id,
                    job_attempt=1,
                    status="pending",
                    attempts=0,
                )
            )

    with pytest.raises(IntegrityError):
        await recovery.begin_expired_recovery(
            "demo-org",
            job_id,
        )

    saved = await jobs.get("demo-org", job_id)
    operations = await find_operations(factory, job_id)

    assert saved.status == "processing"
    assert saved.lease_token == token
    assert saved.worker_id == "fictional-worker-A"
    assert len(operations) == 1
