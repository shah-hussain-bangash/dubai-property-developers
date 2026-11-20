"""Real PostgreSQL and Redis guarded recovery integration tests.

Development-only tests.

Safety:
- Use fictional, unique PostgreSQL job IDs.
- Use isolated Redis keys starting with test:guarded-real:.
- Never access production/application queue keys.
- Clean up created PostgreSQL records and Redis keys.
- Do not connect the recovery coordinator to the Docker worker.

Run with RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

import apps.worker.jobs.guarded_recovery_transition as guarded_module
from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.guarded_recovery_transition import (
    GuardedRecoveryError,
    GuardedRecoveryTransition,
)
from apps.worker.jobs.redis_recovery_evidence import (
    recovery_evidence_key,
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
        reason="Integration tests disabled",
    ),
]

TENANT = "demo-org"
WORKER = "test-real-redis-coordinator"

# Dedicated local development Redis connection.
# Never replace this with a production Redis URL.
TEST_REDIS_URL = "redis://127.0.0.1:6379/0"
TEST_PREFIX = "test:guarded-real:"


# ---------------------------------------------------------
# SHARED FIXTURE: REAL POSTGRESQL AND REAL REDIS
# ---------------------------------------------------------


@pytest.fixture
async def environment():
    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)

    client = redis_asyncio.from_url(
        TEST_REDIS_URL,
        decode_responses=True,
    )

    jobs = PostgresBackgroundJobStore(factory)
    recovery = PostgresJobRecoveryOperationStore(factory)
    leases = PostgresRecoveryLeaseStore(factory)
    guarded = GuardedRecoveryTransition(factory)

    created_job_ids = []
    created_redis_keys = []

    try:
        await client.ping()

        yield {
            "jobs": jobs,
            "recovery": recovery,
            "leases": leases,
            "guarded": guarded,
            "factory": factory,
            "redis": client,
            "job_ids": created_job_ids,
            "redis_keys": created_redis_keys,
        }

    finally:
        try:
            if created_redis_keys:
                await client.delete(*created_redis_keys)
        finally:
            try:
                if created_job_ids:
                    async with factory() as session, session.begin():
                        await session.execute(
                            delete(JobRecoveryOperation).where(
                                JobRecoveryOperation.job_id.in_(created_job_ids)
                            )
                        )
                        await session.execute(
                            delete(BackgroundJob).where(BackgroundJob.job_id.in_(created_job_ids))
                        )
            finally:
                await client.aclose()
                await engine.dispose()


# ---------------------------------------------------------
# HELPER: CREATE FICTIONAL RECOVERY CASE
# ---------------------------------------------------------


async def create_case(environment):
    job_id = "test-guarded-real-" + uuid.uuid4().hex
    environment["job_ids"].append(job_id)

    job = JobEnvelope(
        job_id=job_id,
        job_type="knowledge.ingest",
        tenant_id=TENANT,
        payload={"test": "isolated-real-redis"},
        max_attempts=3,
    )

    record = await environment["jobs"].register(
        TENANT,
        job_id,
        job.job_type,
        max_attempts=job.max_attempts,
    )

    original_token = await environment["jobs"].claim(
        TENANT,
        job_id,
        "test-original-worker",
    )
    assert original_token is not None

    async with environment["factory"]() as session, session.begin():
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == record.id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    operation_id = await environment["recovery"].begin_expired_recovery(
        TENANT,
        job_id,
    )
    assert operation_id is not None

    token = await environment["leases"].claim(
        TENANT,
        operation_id,
        WORKER,
    )
    assert token is not None

    prefix = TEST_PREFIX + uuid.uuid4().hex

    processing_key = prefix + ":processing"
    pending_key = prefix + ":pending"
    evidence_key = recovery_evidence_key(operation_id)

    environment["redis_keys"].extend([processing_key, pending_key, evidence_key])

    # Only these unique test keys are removed.
    await environment["redis"].delete(
        processing_key,
        pending_key,
        evidence_key,
    )

    return {
        "job": job,
        "raw": job.model_dump_json(),
        "operation_id": operation_id,
        "token": token,
        "processing_key": processing_key,
        "pending_key": pending_key,
        "evidence_key": evidence_key,
    }


# ---------------------------------------------------------
# HELPER: INVOKE GUARDED RECOVERY
# ---------------------------------------------------------


async def invoke(environment, case, *, token=None):
    return await environment["guarded"].requeue(
        redis=environment["redis"],
        job=case["job"],
        raw=case["raw"],
        operation_id=case["operation_id"],
        worker_id=WORKER,
        lease_token=(case["token"] if token is None else token),
        processing_key=case["processing_key"],
        pending_key=case["pending_key"],
    )


# ---------------------------------------------------------
# TEST 1: VALID OWNER MOVES REAL REDIS RESERVATION
# ---------------------------------------------------------


async def test_real_redis_valid_owner_moves_reservation(
    environment,
):
    case = await create_case(environment)
    client = environment["redis"]

    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    result = await invoke(environment, case)

    assert result == "moved"

    assert await client.lrange(case["processing_key"], 0, -1) == []

    assert await client.lrange(case["pending_key"], 0, -1) == [case["raw"]]

    assert await client.get(case["evidence_key"]) == "moved"


# ---------------------------------------------------------
# TEST 2: REPLAY DOES NOT DUPLICATE JOB
# ---------------------------------------------------------


async def test_real_redis_replay_does_not_duplicate_job(
    environment,
):
    case = await create_case(environment)
    client = environment["redis"]

    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    first_result = await invoke(environment, case)
    second_result = await invoke(environment, case)

    assert first_result == "moved"
    assert second_result == "already_moved"

    pending = await client.lrange(case["pending_key"], 0, -1)

    assert pending == [case["raw"]]

    assert await client.llen(case["processing_key"]) == 0


# ---------------------------------------------------------
# TEST 3: WRONG LEASE TOKEN CANNOT MOVE RESERVATION
# ---------------------------------------------------------


async def test_real_redis_wrong_token_cannot_move_reservation(
    environment,
):
    case = await create_case(environment)
    client = environment["redis"]

    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    with pytest.raises(
        GuardedRecoveryError,
        match="Recovery lease is not currently owned",
    ):
        await invoke(
            environment,
            case,
            token="incorrect-lease-token",
        )

    assert await client.lrange(case["processing_key"], 0, -1) == [case["raw"]]

    assert await client.llen(case["pending_key"]) == 0

    assert await client.exists(case["evidence_key"]) == 0


# ---------------------------------------------------------
# TEST 4: MISSING RESERVATION REMAINS UNCERTAIN
# ---------------------------------------------------------


async def test_real_redis_missing_reservation_is_uncertain(
    environment,
):
    case = await create_case(environment)
    client = environment["redis"]

    with pytest.raises(
        GuardedRecoveryError,
        match="Redis reconciliation uncertain: missing",
    ):
        await invoke(environment, case)

    assert await client.llen(case["pending_key"]) == 0

    assert await client.exists(case["evidence_key"]) == 0


# ---------------------------------------------------------
# TEST 5: DUPLICATE RESERVATION IS AMBIGUOUS
# ---------------------------------------------------------


async def test_real_redis_duplicate_reservation_is_ambiguous(
    environment,
):
    case = await create_case(environment)
    client = environment["redis"]

    await client.lpush(
        case["processing_key"],
        case["raw"],
        case["raw"],
    )

    with pytest.raises(
        GuardedRecoveryError,
        match="Redis reconciliation uncertain: ambiguous",
    ):
        await invoke(environment, case)

    assert await client.llen(case["processing_key"]) == 2

    assert await client.llen(case["pending_key"]) == 0

    assert await client.exists(case["evidence_key"]) == 0


# ---------------------------------------------------------
# TEST 6: POSTGRESQL ROW-LOCK CONCURRENCY
# ---------------------------------------------------------


async def test_postgres_row_lock_blocks_competing_recovery(
    environment,
    monkeypatch,
):
    """Verify that a guarded transition holds its row lock.

    A competing PostgreSQL transaction must not acquire
    the same recovery-operation lock using NOWAIT.
    """

    case = await create_case(environment)
    client = environment["redis"]

    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    entered_transition = asyncio.Event()
    allow_transition = asyncio.Event()

    original_requeue = guarded_module.requeue_with_evidence

    async def paused_requeue(*args, **kwargs):
        entered_transition.set()
        await allow_transition.wait()
        return await original_requeue(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        guarded_module,
        "requeue_with_evidence",
        paused_requeue,
    )

    transition_task = asyncio.create_task(invoke(environment, case))

    lock_rejected = False

    try:
        await asyncio.wait_for(
            entered_transition.wait(),
            timeout=10,
        )

        assert not transition_task.done()

        async with environment["factory"]() as session:
            try:
                async with session.begin():
                    await session.scalar(
                        select(JobRecoveryOperation)
                        .where(JobRecoveryOperation.id == case["operation_id"])
                        .with_for_update(nowait=True)
                    )
            except DBAPIError as exc:
                sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)

                assert sqlstate == "55P03"
                lock_rejected = True

        assert lock_rejected, (
            "Competing coordinator unexpectedly acquired the recovery-operation row lock"
        )

    finally:
        allow_transition.set()

        if not transition_task.done():
            try:
                await asyncio.wait_for(
                    transition_task,
                    timeout=15,
                )
            except TimeoutError:
                transition_task.cancel()

                await asyncio.gather(
                    transition_task,
                    return_exceptions=True,
                )
                raise

    assert transition_task.result() == "moved"

    assert (
        await client.lrange(
            case["processing_key"],
            0,
            -1,
        )
        == []
    )

    assert await client.lrange(
        case["pending_key"],
        0,
        -1,
    ) == [case["raw"]]

    assert await client.get(case["evidence_key"]) == "moved"


# ---------------------------------------------------------
# TEST 7: EXPIRED LEASE TAKEOVER REJECTS STALE OWNER
# ---------------------------------------------------------


async def test_expired_lease_takeover_rejects_stale_owner(
    environment,
):
    """An expired lease can be reclaimed by another coordinator.

    The old coordinator's token must not authorize
    a new Redis transition after ownership changes.
    """

    case = await create_case(environment)
    client = environment["redis"]
    factory = environment["factory"]

    old_token = case["token"]
    new_worker = "test-takeover-coordinator-B"

    # Add a fictional reservation to the isolated test list.
    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    # Simulate expiration of Coordinator A's lease.
    async with factory() as session, session.begin():
        await session.execute(
            update(JobRecoveryOperation)
            .where(JobRecoveryOperation.id == case["operation_id"])
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    # Coordinator B claims the expired recovery operation.
    new_token = await environment["leases"].claim(
        TENANT,
        case["operation_id"],
        new_worker,
    )

    assert new_token is not None
    assert new_token != old_token

    # Coordinator A's stale token must be rejected.
    with pytest.raises(
        GuardedRecoveryError,
        match="Recovery lease is not currently owned",
    ):
        await invoke(
            environment,
            case,
            token=old_token,
        )

    # The stale request must not modify Redis.
    assert await client.lrange(
        case["processing_key"],
        0,
        -1,
    ) == [case["raw"]]

    assert await client.llen(case["pending_key"]) == 0

    assert await client.exists(case["evidence_key"]) == 0

    # Coordinator B now performs the authorized transition.
    result = await environment["guarded"].requeue(
        redis=client,
        job=case["job"],
        raw=case["raw"],
        operation_id=case["operation_id"],
        worker_id=new_worker,
        lease_token=new_token,
        processing_key=case["processing_key"],
        pending_key=case["pending_key"],
    )

    assert result == "moved"

    assert (
        await client.lrange(
            case["processing_key"],
            0,
            -1,
        )
        == []
    )

    assert await client.lrange(
        case["pending_key"],
        0,
        -1,
    ) == [case["raw"]]

    assert await client.get(case["evidence_key"]) == "moved"


# ---------------------------------------------------------
# TEST 8: REDIS TIMEOUT RELEASES POSTGRESQL ROW LOCK
# ---------------------------------------------------------


async def test_redis_timeout_releases_postgres_lock(
    environment,
    monkeypatch,
):
    """A stalled Redis coroutine times out and releases the PG lock."""

    case = await create_case(environment)
    client = environment["redis"]

    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    entered_redis = asyncio.Event()
    cancelled_redis = asyncio.Event()

    async def stalled_requeue(*args, **kwargs):
        entered_redis.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled_redis.set()

    monkeypatch.setattr(
        guarded_module,
        "requeue_with_evidence",
        stalled_requeue,
    )

    with pytest.raises(
        GuardedRecoveryError,
        match="Redis recovery transition timed out",
    ):
        await environment["guarded"].requeue(
            redis=client,
            job=case["job"],
            raw=case["raw"],
            operation_id=case["operation_id"],
            worker_id=WORKER,
            lease_token=case["token"],
            processing_key=case["processing_key"],
            pending_key=case["pending_key"],
            redis_timeout_seconds=0.2,
        )

    assert entered_redis.is_set()
    assert cancelled_redis.is_set()

    # Confirm the timed-out transaction released its row lock.
    async with environment["factory"]() as session, session.begin():
        operation = await session.scalar(
            select(JobRecoveryOperation)
            .where(JobRecoveryOperation.id == case["operation_id"])
            .with_for_update(nowait=True)
        )
        assert operation is not None

    # The simulated stall issued no Redis transition.
    assert await client.lrange(case["processing_key"], 0, -1) == [case["raw"]]

    assert await client.llen(case["pending_key"]) == 0

    assert await client.exists(case["evidence_key"]) == 0
