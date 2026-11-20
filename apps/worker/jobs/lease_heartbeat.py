"""Lease renewal while a PostgreSQL-backed job handler runs.

This helper is not wired into the deployed worker.

If a heartbeat is rejected or raises an error, the handler task is
cancelled and the lease failure is reported to its caller.

Cancellation is cooperative: synchronous or cancellation-resistant
external operations may continue. External side effects therefore
still need their own idempotency safeguards.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from database.repositories.postgres_background_job_store import (
    PostgresBackgroundJobStore,
)

T = TypeVar("T")


class LeaseHeartbeatLost(RuntimeError):
    """The worker could not confirm continued job ownership."""


async def run_with_lease_heartbeat(  # noqa: UP047 -- Retain the existing shared TypeVar signature.
    handler_coroutine: Coroutine[Any, Any, T],
    *,
    store: PostgresBackgroundJobStore,
    tenant_id: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    lease_seconds: int = 120,
    heartbeat_interval_seconds: float | None = None,
) -> T:
    """Run a handler while periodically renewing its PostgreSQL lease.

    Returns the handler result if it finishes normally.

    Raises LeaseHeartbeatLost if renewal is refused or fails.
    Propagates handler exceptions and cancellation.

    This does not complete/fail the PostgreSQL job or acknowledge Redis.
    """

    if not isinstance(lease_seconds, int) or lease_seconds < 1:
        handler_coroutine.close()
        raise ValueError("lease_seconds must be a positive integer")

    interval = (
        lease_seconds / 3 if heartbeat_interval_seconds is None else heartbeat_interval_seconds
    )

    if not isinstance(interval, (int, float)) or not (0 < interval < lease_seconds):
        handler_coroutine.close()
        raise ValueError("Heartbeat interval must be greater than zero and shorter than the lease")

    async def renew_lease() -> None:
        while True:
            await asyncio.sleep(interval)

            renewed = await store.heartbeat(
                tenant_id,
                job_id,
                worker_id,
                lease_token,
                lease_seconds=lease_seconds,
            )

            if not renewed:
                raise LeaseHeartbeatLost("PostgreSQL processing lease renewal was rejected")

    handler_task = asyncio.create_task(
        handler_coroutine,
        name="postgres-job-handler",
    )
    heartbeat_task = asyncio.create_task(
        renew_lease(),
        name="postgres-job-heartbeat",
    )

    try:
        done, _ = await asyncio.wait(
            {handler_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Heartbeat failure takes priority if both tasks finish
        # during the same event-loop scheduling window.
        if heartbeat_task in done or heartbeat_task.done():
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                raise
            except LeaseHeartbeatLost:
                raise
            except Exception as exc:
                raise LeaseHeartbeatLost("PostgreSQL heartbeat failed") from exc

            raise LeaseHeartbeatLost("Heartbeat task ended unexpectedly")

        # The handler finished before heartbeat failure.
        # Its own exception, if any, is propagated.
        return await handler_task

    finally:
        # Stop the handler on lease loss, and stop renewal when
        # the handler finishes or the caller is cancelled.
        for task in (handler_task, heartbeat_task):
            if not task.done():
                task.cancel()

        await asyncio.gather(
            handler_task,
            heartbeat_task,
            return_exceptions=True,
        )
