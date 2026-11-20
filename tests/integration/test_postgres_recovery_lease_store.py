"""Integration tests for PostgreSQL recovery-operation ownership.

Requires PostgreSQL migration 0006 and RUN_INTEGRATION_TESTS=1.

Uses fictional jobs only. Does not access Redis, execute handlers,
or modify existing jobs. All created records are cleaned up.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

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


@pytest.fixture
async def recovery_setup():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    jobs = PostgresBackgroundJobStore(factory)
    recovery = PostgresJobRecoveryOperationStore(factory)
    leases = PostgresRecoveryLeaseStore(factory)

    created_ids = []

    try:
        yield jobs, recovery, leases, factory, created_ids

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


async def create_operation(
    jobs,
    recovery,
    factory,
    created_ids,
):
    job_id = "test-recovery-lease-" + uuid.uuid4().hex
    created_ids.append(job_id)

    record = await jobs.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
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
    )

    assert operation_id is not None

    return operation_id


async def get_operation(factory, operation_id):
    async with factory() as session:
        return await session.scalar(
            select(JobRecoveryOperation).where(JobRecoveryOperation.id == operation_id)
        )


async def test_recovery_operation_can_be_claimed(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-A",
    )

    assert token is not None

    saved = await get_operation(factory, operation_id)

    assert saved.status == "processing"
    assert saved.worker_id == "coordinator-A"
    assert saved.lease_token == token
    assert saved.lease_expires_at is not None
    assert saved.attempts == 1


async def test_only_one_coordinator_claims_operation(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    results = await asyncio.gather(
        leases.claim(
            "demo-org",
            operation_id,
            "coordinator-A",
        ),
        leases.claim(
            "demo-org",
            operation_id,
            "coordinator-B",
        ),
    )

    assert sum(token is not None for token in results) == 1

    saved = await get_operation(factory, operation_id)

    assert saved.status == "processing"
    assert saved.attempts == 1


async def test_heartbeat_requires_correct_owner(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-A",
    )

    assert token is not None

    wrong = await leases.heartbeat(
        "demo-org",
        operation_id,
        "coordinator-B",
        token,
    )

    assert wrong is False

    renewed = await leases.heartbeat(
        "demo-org",
        operation_id,
        "coordinator-A",
        token,
    )

    assert renewed is True


async def test_completion_rejects_stale_token(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-A",
    )

    assert token is not None

    wrong = await leases.complete(
        "demo-org",
        operation_id,
        "coordinator-A",
        "incorrect-token",
    )

    assert wrong is False

    completed = await leases.complete(
        "demo-org",
        operation_id,
        "coordinator-A",
        token,
    )

    assert completed is True

    saved = await get_operation(factory, operation_id)

    assert saved.status == "completed"
    assert saved.completed_at is not None
    assert saved.lease_token is None
    assert saved.worker_id is None

    assert (
        await leases.claim(
            "demo-org",
            operation_id,
            "coordinator-B",
        )
        is None
    )


async def test_failed_recovery_respects_retry_delay(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-A",
    )

    assert token is not None

    failed = await leases.fail(
        "demo-org",
        operation_id,
        "coordinator-A",
        token,
        retry_delay_seconds=3600,
        error_code="redis_unavailable",
    )

    assert failed is True

    saved = await get_operation(factory, operation_id)

    assert saved.status == "retrying"
    assert saved.error_code == "redis_unavailable"
    assert saved.next_attempt_at is not None

    early_claim = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-B",
    )

    assert early_claim is None

    # Simulate the passage of retry time for this test record.
    async with factory() as session, session.begin():
        await session.execute(
            update(JobRecoveryOperation)
            .where(JobRecoveryOperation.id == operation_id)
            .values(next_attempt_at=(datetime.now(UTC) - timedelta(seconds=1)))
        )

    new_token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-B",
    )

    assert new_token is not None
    assert new_token != token

    saved = await get_operation(factory, operation_id)
    assert saved.attempts == 2


async def test_expired_recovery_lease_can_be_reclaimed(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    old_token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-A",
    )

    assert old_token is not None

    async with factory() as session, session.begin():
        await session.execute(
            update(JobRecoveryOperation)
            .where(JobRecoveryOperation.id == operation_id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    new_token = await leases.claim(
        "demo-org",
        operation_id,
        "coordinator-B",
    )

    assert new_token is not None
    assert new_token != old_token

    stale_completion = await leases.complete(
        "demo-org",
        operation_id,
        "coordinator-A",
        old_token,
    )

    assert stale_completion is False

    saved = await get_operation(factory, operation_id)

    assert saved.worker_id == "coordinator-B"
    assert saved.lease_token == new_token
    assert saved.attempts == 2


async def test_wrong_tenant_cannot_claim_operation(
    recovery_setup,
):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(jobs, recovery, factory, ids)

    token = await leases.claim(
        "tenant-isolation-test",
        operation_id,
        "coordinator-B",
    )

    assert token is None

    saved = await get_operation(factory, operation_id)

    assert saved.status == "pending"
    assert saved.worker_id is None
