"""Unit tests for PostgreSQL lease heartbeat management.

Uses mocked database operations. No real services are contacted.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.lease_heartbeat import (
    LeaseHeartbeatLost,
    run_with_lease_heartbeat,
)


def make_store(*, renewed=True):
    return SimpleNamespace(heartbeat=AsyncMock(return_value=renewed))


async def run_test_handler(store, coroutine, *, interval=0.01):
    return await run_with_lease_heartbeat(
        coroutine,
        store=store,
        tenant_id="demo-org",
        job_id="fictional-heartbeat-job",
        worker_id="worker-A",
        lease_token="fictional-lease-token",
        lease_seconds=3,
        heartbeat_interval_seconds=interval,
    )


@pytest.mark.asyncio
async def test_short_job_completes_without_heartbeat():
    store = make_store()

    async def handler():
        return {"ok": True}

    result = await run_test_handler(store, handler())

    assert result == {"ok": True}
    store.heartbeat.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_job_renews_lease():
    store = make_store()

    async def handler():
        await asyncio.sleep(0.06)
        return "finished"

    result = await run_test_handler(store, handler())

    assert result == "finished"
    assert store.heartbeat.await_count >= 1

    store.heartbeat.assert_any_await(
        "demo-org",
        "fictional-heartbeat-job",
        "worker-A",
        "fictional-lease-token",
        lease_seconds=3,
    )


@pytest.mark.asyncio
async def test_rejected_heartbeat_cancels_handler():
    store = make_store(renewed=False)
    handler_cancelled = asyncio.Event()

    async def handler():
        try:
            await asyncio.sleep(10)
        finally:
            handler_cancelled.set()

    with pytest.raises(
        LeaseHeartbeatLost,
        match="renewal was rejected",
    ):
        await run_test_handler(store, handler())

    assert handler_cancelled.is_set()
    store.heartbeat.assert_awaited()


@pytest.mark.asyncio
async def test_database_heartbeat_error_stops_handler():
    store = make_store()
    store.heartbeat.side_effect = ConnectionError("Fictional database outage")

    handler_cancelled = asyncio.Event()

    async def handler():
        try:
            await asyncio.sleep(10)
        finally:
            handler_cancelled.set()

    with pytest.raises(
        LeaseHeartbeatLost,
        match="PostgreSQL heartbeat failed",
    ):
        await run_test_handler(store, handler())

    assert handler_cancelled.is_set()


@pytest.mark.asyncio
async def test_handler_failure_is_propagated():
    store = make_store()

    async def handler():
        raise ValueError("Fictional handler failure")

    with pytest.raises(
        ValueError,
        match="Fictional handler failure",
    ):
        await run_test_handler(store, handler())


@pytest.mark.asyncio
async def test_caller_cancellation_stops_handler():
    store = make_store()
    handler_started = asyncio.Event()
    handler_cancelled = asyncio.Event()

    async def handler():
        handler_started.set()
        try:
            await asyncio.sleep(10)
        finally:
            handler_cancelled.set()

    task = asyncio.create_task(run_test_handler(store, handler()))

    await asyncio.wait_for(handler_started.wait(), timeout=2)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert handler_cancelled.is_set()


@pytest.mark.asyncio
async def test_invalid_heartbeat_interval_is_rejected():
    store = make_store()

    async def handler():
        return "unused"

    with pytest.raises(
        ValueError,
        match="Heartbeat interval",
    ):
        await run_with_lease_heartbeat(
            handler(),
            store=store,
            tenant_id="demo-org",
            job_id="fictional-job",
            worker_id="worker-A",
            lease_token="fictional-token",
            lease_seconds=3,
            heartbeat_interval_seconds=5,
        )

    store.heartbeat.assert_not_awaited()
