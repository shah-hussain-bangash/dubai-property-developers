
"""Unit tests for the read-only Redis reservation inspector.

Development-only.
Uses mocked Redis and does not modify real queues.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.redis_reservation_inspector import (
    inspect_reservation,
)


PROCESSING = "test:inspection:processing"
PENDING = "test:inspection:pending"
RAW = '{"job_id":"fictional-inspection-job"}'


def make_redis(processing_positions, pending_positions):
    redis = AsyncMock()
    redis.lpos.side_effect = [
        processing_positions,
        pending_positions,
    ]
    return redis


async def invoke(redis):
    return await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )


@pytest.mark.asyncio
async def test_single_processing_reservation():
    redis = make_redis([0], None)

    result = await invoke(redis)

    assert result == "processing"
    assert redis.lpos.await_count == 2
    redis.lpos.assert_any_await(
        PROCESSING, RAW, count=0
    )
    redis.lpos.assert_any_await(
        PENDING, RAW, count=0
    )


@pytest.mark.asyncio
async def test_single_pending_reservation():
    redis = make_redis(None, [0])

    assert await invoke(redis) == "pending"


@pytest.mark.asyncio
async def test_missing_reservation():
    redis = make_redis(None, None)

    assert await invoke(redis) == "missing"


@pytest.mark.asyncio
async def test_duplicate_processing_is_ambiguous():
    redis = make_redis([0, 1], None)

    assert await invoke(redis) == "ambiguous"


@pytest.mark.asyncio
async def test_duplicate_pending_is_ambiguous():
    redis = make_redis(None, [0, 1])

    assert await invoke(redis) == "ambiguous"


@pytest.mark.asyncio
async def test_processing_and_pending_is_ambiguous():
    redis = make_redis([0], [0])

    assert await invoke(redis) == "ambiguous"


@pytest.mark.asyncio
async def test_redis_connection_error_propagates():
    redis = AsyncMock()
    redis.lpos.side_effect = ConnectionError(
        "Redis unavailable"
    )

    with pytest.raises(ConnectionError):
        await invoke(redis)


@pytest.mark.asyncio
async def test_empty_raw_is_rejected():
    redis = AsyncMock()

    with pytest.raises(ValueError, match="raw message"):
        await inspect_reservation(
            redis,
            "",
            processing_key=PROCESSING,
            pending_key=PENDING,
        )

    redis.lpos.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_processing_key_is_rejected():
    redis = AsyncMock()

    with pytest.raises(ValueError, match="queue keys"):
        await inspect_reservation(
            redis,
            RAW,
            processing_key="",
            pending_key=PENDING,
        )

    redis.lpos.assert_not_awaited()


@pytest.mark.asyncio
async def test_identical_queue_keys_are_rejected():
    redis = AsyncMock()

    with pytest.raises(ValueError, match="must differ"):
        await inspect_reservation(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PROCESSING,
        )

    redis.lpos.assert_not_awaited()


@pytest.mark.asyncio
async def test_inspection_does_not_write_to_redis():
    redis = make_redis([0], None)

    assert await invoke(redis) == "processing"

    redis.lrem.assert_not_awaited()
    redis.lpush.assert_not_awaited()
    redis.set.assert_not_awaited()
    redis.delete.assert_not_awaited()
