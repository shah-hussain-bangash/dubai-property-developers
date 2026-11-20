"""Integration tests for PostgreSQL background-job persistence.

Requires:
    RUN_INTEGRATION_TESTS=1
    PostgreSQL with migration 0004 applied

Uses fictional job identifiers and cleans up test data.
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
from database.sessions.engine import create_engine, create_session_factory

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL integration tests are disabled",
    ),
]


@pytest.fixture
async def job_store():
    """Create an isolated repository and clean up its test records."""

    settings = Settings()

    if not settings.is_dev_like:
        pytest.skip("Development environment required")

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PostgresBackgroundJobStore(factory)

    created_ids: list[str] = []

    try:
        yield store, factory, created_ids

    finally:
        try:
            if created_ids:
                async with factory() as session, session.begin():
                    await session.execute(
                        delete(BackgroundJob).where(BackgroundJob.job_id.in_(created_ids))
                    )
        finally:
            await engine.dispose()


def new_job_id(created_ids: list[str]) -> str:
    job_id = f"test-{uuid.uuid4().hex}"
    created_ids.append(job_id)
    return job_id


async def test_registration_and_tenant_isolation(job_store):
    store, _, created_ids = job_store

    job_id = new_job_id(created_ids)

    first = await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
    )

    second = await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
    )

    assert first.id == second.id
    assert first.status == "pending"

    saved = await store.get("demo-org", job_id)
    assert saved is not None

    invisible = await store.get(
        "tenant-isolation-test",
        job_id,
    )
    assert invisible is None


async def test_only_one_worker_can_claim_job(job_store):
    store, _, created_ids = job_store

    job_id = new_job_id(created_ids)

    await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
    )

    claims = await asyncio.gather(
        store.claim("demo-org", job_id, "worker-A"),
        store.claim("demo-org", job_id, "worker-B"),
    )

    assert sum(token is not None for token in claims) == 1

    saved = await store.get("demo-org", job_id)
    assert saved.status == "processing"
    assert saved.attempts == 1


async def test_heartbeat_and_lease_ownership(job_store):
    store, _, created_ids = job_store

    job_id = new_job_id(created_ids)

    await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
    )

    token = await store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    wrong = await store.heartbeat(
        "demo-org",
        job_id,
        "worker-B",
        token,
    )
    assert wrong is False

    renewed = await store.heartbeat(
        "demo-org",
        job_id,
        "worker-A",
        token,
    )
    assert renewed is True


async def test_failure_retry_and_completion(job_store):
    store, _, created_ids = job_store

    job_id = new_job_id(created_ids)

    await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
        max_attempts=3,
    )

    first_token = await store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert first_token is not None

    status = await store.fail(
        "demo-org",
        job_id,
        "worker-A",
        first_token,
        retry_delay_seconds=0,
        error_code="handler_error",
    )

    assert status == "retrying"

    second_token = await store.claim(
        "demo-org",
        job_id,
        "worker-B",
    )

    assert second_token is not None
    assert second_token != first_token

    stale_completion = await store.complete(
        "demo-org",
        job_id,
        "worker-A",
        first_token,
    )

    assert stale_completion is False

    completed = await store.complete(
        "demo-org",
        job_id,
        "worker-B",
        second_token,
    )

    assert completed is True

    saved = await store.get("demo-org", job_id)

    assert saved.status == "succeeded"
    assert saved.attempts == 2
    assert saved.finished_at is not None


async def test_expired_lease_discovery(job_store):
    store, factory, created_ids = job_store

    job_id = new_job_id(created_ids)

    record = await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
    )

    token = await store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    async with factory() as session, session.begin():
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == record.id)
            .values(lease_expires_at=(datetime.now(UTC) - timedelta(minutes=5)))
        )

    expired = await store.list_expired(limit=100)

    assert any(item.id == record.id for item in expired)

    completed = await store.complete(
        "demo-org",
        job_id,
        "worker-A",
        token,
    )

    assert completed is False


async def test_maximum_attempts_results_in_failure(job_store):
    store, _, created_ids = job_store

    job_id = new_job_id(created_ids)

    await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
        max_attempts=1,
    )

    token = await store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    status = await store.fail(
        "demo-org",
        job_id,
        "worker-A",
        token,
        error_code="handler_error",
    )

    assert status == "failed"

    another_claim = await store.claim(
        "demo-org",
        job_id,
        "worker-B",
    )

    assert another_claim is None


async def test_retry_delay_is_enforced(job_store):
    store, _, created_ids = job_store

    job_id = new_job_id(created_ids)

    await store.register(
        "demo-org",
        job_id,
        "knowledge.ingest",
    )

    token = await store.claim(
        "demo-org",
        job_id,
        "worker-A",
    )

    assert token is not None

    status = await store.fail(
        "demo-org",
        job_id,
        "worker-A",
        token,
        retry_delay_seconds=3600,
    )

    assert status == "retrying"

    immediate_claim = await store.claim(
        "demo-org",
        job_id,
        "worker-B",
    )

    assert immediate_claim is None

    saved = await store.get("demo-org", job_id)

    assert saved.next_retry_at is not None
