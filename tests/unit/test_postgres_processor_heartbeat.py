"""Processor integration tests for automatic lease heartbeats.

All dependencies are mocked. No database or Redis connections.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.lease_heartbeat import LeaseHeartbeatLost
from apps.worker.jobs.postgres_processor import process_postgres_job


def setup_job():
    job = JobEnvelope(
        job_id="fictional-heartbeat-processor-job",
        tenant_id="demo-org",
        job_type="knowledge.ingest",
        payload={"document_id": "fictional-document"},
        max_attempts=3,
    )

    record = SimpleNamespace(
        job_type=job.job_type,
        max_attempts=job.max_attempts,
        status="pending",
    )

    store = SimpleNamespace(
        get=AsyncMock(return_value=record),
        claim=AsyncMock(return_value="lease-token-A"),
        heartbeat=AsyncMock(return_value=True),
        complete=AsyncMock(return_value=True),
        fail=AsyncMock(return_value="retrying"),
    )

    authenticator = SimpleNamespace(
        authenticate=AsyncMock(return_value=job),
    )

    return job, store, authenticator


@pytest.mark.asyncio
async def test_long_running_handler_renews_lease():
    job, store, authenticator = setup_job()
    redis = object()

    async def handler(runtime, received_job):
        assert received_job == job
        await asyncio.sleep(0.06)
        return {"ok": True}

    with (
        patch(
            "apps.worker.jobs.postgres_processor.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.jobs.postgres_processor.acknowledge_job",
            new_callable=AsyncMock,
            return_value=True,
        ) as acknowledge,
    ):
        result = await process_postgres_job(
            object(),
            redis,
            job.model_dump_json(),
            store,
            authenticator=authenticator,
            worker_id="worker-A",
            lease_seconds=3,
            heartbeat_interval_seconds=0.01,
        )

    assert result == "succeeded"
    assert store.heartbeat.await_count >= 1
    store.complete.assert_awaited_once()
    store.fail.assert_not_awaited()
    acknowledge.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejected_lease_does_not_complete_fail_or_ack():
    job, store, authenticator = setup_job()
    store.heartbeat.return_value = False

    handler_cancelled = asyncio.Event()

    async def handler(runtime, received_job):
        try:
            await asyncio.sleep(10)
        finally:
            handler_cancelled.set()

    with (
        patch(
            "apps.worker.jobs.postgres_processor.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.jobs.postgres_processor.acknowledge_job",
            new_callable=AsyncMock,
        ) as acknowledge,
        pytest.raises(
            LeaseHeartbeatLost,
            match="renewal was rejected",
        ),
    ):
        await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=authenticator,
            worker_id="worker-A",
            lease_seconds=3,
            heartbeat_interval_seconds=0.01,
        )

    assert handler_cancelled.is_set()
    store.fail.assert_not_awaited()
    store.complete.assert_not_awaited()
    acknowledge.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_database_outage_is_not_handler_failure():
    job, store, authenticator = setup_job()

    store.heartbeat.side_effect = ConnectionError("Fictional PostgreSQL outage")

    async def handler(runtime, received_job):
        await asyncio.sleep(10)

    with (
        patch(
            "apps.worker.jobs.postgres_processor.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.jobs.postgres_processor.acknowledge_job",
            new_callable=AsyncMock,
        ) as acknowledge,
        pytest.raises(
            LeaseHeartbeatLost,
            match="PostgreSQL heartbeat failed",
        ),
    ):
        await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=authenticator,
            worker_id="worker-A",
            lease_seconds=3,
            heartbeat_interval_seconds=0.01,
        )

    store.fail.assert_not_awaited()
    store.complete.assert_not_awaited()
    acknowledge.assert_not_awaited()
