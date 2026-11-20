"""Tests for PostgreSQL heartbeat cancellation cleanup.

Uses mocked PostgreSQL operations.
No Redis, Docker, network, or real database access.

This test demonstrates cooperative cancellation cleanup.
It does not prove protection against handlers that never stop.
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


@pytest.mark.asyncio
async def test_lease_loss_waits_for_handler_cleanup():
    store = SimpleNamespace(heartbeat=AsyncMock(return_value=False))

    handler_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    wrapper_finished = asyncio.Event()

    async def handler():
        handler_started.set()

        try:
            await asyncio.sleep(10)

        except asyncio.CancelledError:
            # Simulate an agent performing asynchronous cleanup.
            cleanup_started.set()
            await allow_cleanup.wait()
            raise

    async def invoke():
        try:
            await run_with_lease_heartbeat(
                handler(),
                store=store,
                tenant_id="demo-org",
                job_id="fictional-cleanup-job",
                worker_id="worker-A",
                lease_token="fictional-token",
                lease_seconds=3,
                heartbeat_interval_seconds=0.01,
            )
        finally:
            wrapper_finished.set()

    task = asyncio.create_task(invoke())

    try:
        await asyncio.wait_for(
            handler_started.wait(),
            timeout=2,
        )

        await asyncio.wait_for(
            cleanup_started.wait(),
            timeout=2,
        )

        # The wrapper must not return while cleanup is pending.
        assert not task.done()
        assert not wrapper_finished.is_set()

    finally:
        # Release cleanup even if an assertion fails.
        allow_cleanup.set()

        try:
            with pytest.raises(LeaseHeartbeatLost):
                await asyncio.wait_for(task, timeout=2)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(
                    task,
                    return_exceptions=True,
                )

    assert wrapper_finished.is_set()
    store.heartbeat.assert_awaited()
