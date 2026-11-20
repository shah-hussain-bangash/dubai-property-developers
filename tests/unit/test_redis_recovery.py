
"""Unit tests for isolated Redis recovery operations.

No real Redis or PostgreSQL access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.redis_recovery import (
    RECOVER_SCRIPT,
    ACK_STALE_SCRIPT,
    acknowledge_stale_reservation,
    requeue_reserved_job,
)


PROCESSING = "queue:jobs:processing:test"
PENDING = "queue:jobs:pending:test"
RAW = '{"job_id":"fictional-recovery-job"}'


@pytest.mark.asyncio
async def test_requeue_uses_atomic_redis_script():
    redis = AsyncMock()
    redis.eval.return_value = 1

    result = await requeue_reserved_job(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result is True
    redis.eval.assert_awaited_once_with(
        RECOVER_SCRIPT,
        2,
        PROCESSING,
        PENDING,
        RAW,
    )


@pytest.mark.asyncio
async def test_missing_reservation_does_not_requeue():
    redis = AsyncMock()
    redis.eval.return_value = 0

    result = await requeue_reserved_job(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result is False


@pytest.mark.asyncio
async def test_stale_reservation_is_acknowledged():
    redis = AsyncMock()
    redis.eval.return_value = 1

    result = await acknowledge_stale_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
    )

    assert result is True
    redis.eval.assert_awaited_once_with(
        ACK_STALE_SCRIPT,
        1,
        PROCESSING,
        RAW,
    )


@pytest.mark.asyncio
async def test_missing_stale_reservation_returns_false():
    redis = AsyncMock()
    redis.eval.return_value = 0

    result = await acknowledge_stale_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
    )

    assert result is False


@pytest.mark.asyncio
async def test_requeue_rejects_identical_queue_keys():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="must differ",
    ):
        await requeue_reserved_job(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PROCESSING,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_requeue_requires_message():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="raw message is required",
    ):
        await requeue_reserved_job(
            redis,
            "",
            processing_key=PROCESSING,
            pending_key=PENDING,
        )

    redis.eval.assert_not_awaited()
