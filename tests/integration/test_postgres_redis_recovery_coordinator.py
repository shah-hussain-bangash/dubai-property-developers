"""Integration tests for read-only recovery coordinator authorization.

Requires:
    RUN_INTEGRATION_TESTS=1
    PostgreSQL migration 0006
    Development/test environment

Creates uniquely identified fictional jobs and cleans up their
PostgreSQL records. Does not access Redis or execute job handlers.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.postgres_redis_recovery_coordinator import (
    PostgresRedisRecoveryCoordinator,
    RecoveryAuthorizationError,
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

TENANT = "demo-org"
WORKER = "test-recovery-coordinator"


@pytest.fixture
async def coordinator_setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    jobs = PostgresBackgroundJobStore(factory)
    recovery = PostgresJobRecoveryOperationStore(factory)
    leases = PostgresRecoveryLeaseStore(factory)
    coordinator = PostgresRedisRecoveryCoordinator(factory)

    created_ids: list[str] = []

    try:
        yield jobs, recovery, leases, coordinator, factory, created_ids
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


async def create_recovery_case(
    setup,
    *,
    max_attempts: int = 3,
):
    jobs, recovery, leases, _coordinator, factory, ids = setup

    job_id = "test-coordinator-" + uuid.uuid4().hex
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

    async with factory() as session, session.begin():
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == record.id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
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


async def test_retryable_recovery_is_authorized(coordinator_setup):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, token = await create_recovery_case(setup)

    result = await coordinator.authorize(
        job=job,
        operation_id=operation_id,
        worker_id=WORKER,
        lease_token=token,
    )

    assert result == "requeue"


async def test_exhausted_recovery_requires_acknowledgement(
    coordinator_setup,
):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, token = await create_recovery_case(
        setup,
        max_attempts=1,
    )

    result = await coordinator.authorize(
        job=job,
        operation_id=operation_id,
        worker_id=WORKER,
        lease_token=token,
    )

    assert result == "acknowledge"


async def test_wrong_lease_token_is_rejected(coordinator_setup):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, _ = await create_recovery_case(setup)

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Recovery lease is not currently owned",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=operation_id,
            worker_id=WORKER,
            lease_token="wrong-token",
        )


async def test_wrong_worker_is_rejected(coordinator_setup):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, token = await create_recovery_case(setup)

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Recovery lease is not currently owned",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=operation_id,
            worker_id="different-coordinator",
            lease_token=token,
        )


async def test_expired_lease_is_rejected(coordinator_setup):
    setup = coordinator_setup
    coordinator, factory = setup[3], setup[4]

    job, operation_id, token = await create_recovery_case(setup)

    async with factory() as session, session.begin():
        await session.execute(
            update(JobRecoveryOperation)
            .where(JobRecoveryOperation.id == operation_id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Recovery lease is not currently owned",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=operation_id,
            worker_id=WORKER,
            lease_token=token,
        )


async def test_wrong_tenant_is_rejected(coordinator_setup):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, token = await create_recovery_case(setup)

    wrong_tenant_job = job.model_copy(update={"tenant_id": "tenant-isolation-test"})

    with pytest.raises(RecoveryAuthorizationError):
        await coordinator.authorize(
            job=wrong_tenant_job,
            operation_id=operation_id,
            worker_id=WORKER,
            lease_token=token,
        )


async def test_wrong_operation_id_is_rejected(coordinator_setup):
    setup = coordinator_setup
    coordinator = setup[3]

    job, _, token = await create_recovery_case(setup)

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Recovery operation does not match job",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=uuid.uuid4(),
            worker_id=WORKER,
            lease_token=token,
        )


async def test_mismatched_job_type_is_rejected(coordinator_setup):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, token = await create_recovery_case(setup)

    modified_job = job.model_copy(update={"job_type": "incorrect.job.type"})

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Recovery metadata does not match job",
    ):
        await coordinator.authorize(
            job=modified_job,
            operation_id=operation_id,
            worker_id=WORKER,
            lease_token=token,
        )


async def test_mismatched_max_attempts_is_rejected(
    coordinator_setup,
):
    setup = coordinator_setup
    coordinator = setup[3]

    job, operation_id, token = await create_recovery_case(setup)

    modified_job = job.model_copy(update={"max_attempts": 99})

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Recovery metadata does not match job",
    ):
        await coordinator.authorize(
            job=modified_job,
            operation_id=operation_id,
            worker_id=WORKER,
            lease_token=token,
        )


async def test_ineligible_job_status_is_rejected(
    coordinator_setup,
):
    setup = coordinator_setup
    coordinator, factory = setup[3], setup[4]

    job, operation_id, token = await create_recovery_case(setup)

    async with factory() as session, session.begin():
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.job_id == job.job_id)
            .values(status="processing")
        )

    with pytest.raises(
        RecoveryAuthorizationError,
        match="Background job is not eligible for recovery",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=operation_id,
            worker_id=WORKER,
            lease_token=token,
        )
