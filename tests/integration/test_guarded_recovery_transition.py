
"""Integration tests for guarded recovery authorization.

Uses real development PostgreSQL records and mocked Redis.
Does not access application Redis queues or execute job handlers.

Run with RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, update

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.guarded_recovery_transition import (
    GuardedRecoveryError,
    GuardedRecoveryTransition,
)
from core.config.settings import Settings
from database.models.background_job import BackgroundJob
from database.models.job_recovery_operation import JobRecoveryOperation
from database.repositories.postgres_background_job_store import (
    PostgresBackgroundJobStore,
)
from database.repositories.postgres_job_recovery_operation_store import (
    PostgresJobRecoveryOperationStore,
)
from database.repositories.postgres_recovery_lease_store import (
    PostgresRecoveryLeaseStore,
)
from database.sessions.engine import create_engine, create_session_factory


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration tests disabled",
    ),
]

TENANT = "demo-org"
WORKER = "test-guarded-coordinator"


@pytest.fixture
async def setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    jobs = PostgresBackgroundJobStore(factory)
    recovery = PostgresJobRecoveryOperationStore(factory)
    leases = PostgresRecoveryLeaseStore(factory)
    guarded = GuardedRecoveryTransition(factory)
    created_ids = []

    try:
        yield jobs, recovery, leases, guarded, factory, created_ids
    finally:
        try:
            if created_ids:
                async with factory() as session:
                    async with session.begin():
                        await session.execute(
                            delete(JobRecoveryOperation).where(
                                JobRecoveryOperation.job_id.in_(created_ids)
                            )
                        )
                        await session.execute(
                            delete(BackgroundJob).where(
                                BackgroundJob.job_id.in_(created_ids)
                            )
                        )
        finally:
            await engine.dispose()


async def create_case(setup, *, max_attempts=3):
    jobs, recovery, leases, _, factory, ids = setup

    job_id = "test-guarded-" + uuid.uuid4().hex
    ids.append(job_id)

    job = JobEnvelope(
        job_id=job_id,
        job_type="knowledge.ingest",
        tenant_id=TENANT,
        payload={},
        max_attempts=max_attempts,
    )

    record = await jobs.register(
        TENANT,
        job_id,
        job.job_type,
        max_attempts=max_attempts,
    )

    original_token = await jobs.claim(
        TENANT,
        job_id,
        "test-original-worker",
    )
    assert original_token is not None

    async with factory() as session:
        async with session.begin():
            await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.id == record.id)
                .values(
                    lease_expires_at=datetime.now(UTC)
                    - timedelta(minutes=5)
                )
            )

    operation_id = await recovery.begin_expired_recovery(
        TENANT,
        job_id,
    )
    assert operation_id is not None

    token = await leases.claim(
        TENANT,
        operation_id,
        WORKER,
    )
    assert token is not None

    return job, operation_id, token


async def invoke(setup, job, operation_id, token, redis):
    guarded = setup[3]

    return await guarded.requeue(
        redis=redis,
        job=job,
        raw=job.model_dump_json(),
        operation_id=operation_id,
        worker_id=WORKER,
        lease_token=token,
        processing_key="test:guarded:processing",
        pending_key="test:guarded:pending",
    )


async def test_valid_owner_can_request_transition(setup):
    job, operation_id, token = await create_case(setup)
    redis = AsyncMock()
    redis.eval.return_value = 1

    result = await invoke(setup, job, operation_id, token, redis)

    assert result == "moved"
    redis.eval.assert_awaited_once()


async def test_wrong_token_cannot_access_redis(setup):
    job, operation_id, _ = await create_case(setup)
    redis = AsyncMock()

    with pytest.raises(
        GuardedRecoveryError,
        match="Recovery lease is not currently owned",
    ):
        await invoke(setup, job, operation_id, "wrong-token", redis)

    redis.eval.assert_not_awaited()


async def test_expired_lease_cannot_access_redis(setup):
    job, operation_id, token = await create_case(setup)
    redis = AsyncMock()
    factory = setup[4]

    async with factory() as session:
        async with session.begin():
            await session.execute(
                update(JobRecoveryOperation)
                .where(JobRecoveryOperation.id == operation_id)
                .values(
                    lease_expires_at=datetime.now(UTC)
                    - timedelta(minutes=5)
                )
            )

    with pytest.raises(
        GuardedRecoveryError,
        match="Recovery lease is not currently owned",
    ):
        await invoke(setup, job, operation_id, token, redis)

    redis.eval.assert_not_awaited()


async def test_exhausted_job_cannot_be_requeued(setup):
    job, operation_id, token = await create_case(
        setup,
        max_attempts=1,
    )
    redis = AsyncMock()

    with pytest.raises(
        GuardedRecoveryError,
        match="Background job is not eligible for requeue",
    ):
        await invoke(setup, job, operation_id, token, redis)

    redis.eval.assert_not_awaited()


async def test_wrong_operation_cannot_access_redis(setup):
    job, _, token = await create_case(setup)
    redis = AsyncMock()

    with pytest.raises(
        GuardedRecoveryError,
        match="Recovery operation does not match job",
    ):
        await invoke(setup, job, uuid.uuid4(), token, redis)

    redis.eval.assert_not_awaited()


async def test_missing_reservation_remains_uncertain(setup):
    job, operation_id, token = await create_case(setup)
    redis = AsyncMock()
    redis.eval.return_value = 0

    with pytest.raises(
        GuardedRecoveryError,
        match="Redis reconciliation uncertain: missing",
    ):
        await invoke(setup, job, operation_id, token, redis)


async def test_ambiguous_reservation_remains_uncertain(setup):
    job, operation_id, token = await create_case(setup)
    redis = AsyncMock()
    redis.eval.return_value = 3

    with pytest.raises(
        GuardedRecoveryError,
        match="Redis reconciliation uncertain: ambiguous",
    ):
        await invoke(setup, job, operation_id, token, redis)
