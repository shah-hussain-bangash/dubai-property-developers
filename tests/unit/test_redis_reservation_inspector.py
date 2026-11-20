"""Unit tests for the read-only Redis reservation inspector.

Uses mocked Redis only. No real Redis or PostgreSQL access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.redis_reservation_inspector import (
    inspect_reservation,
)

PROCESSING = "queue:jobs:processing:test"
PENDING = "queue:jobs:pending:test"
RAW = '{"job_id":"fictional-inspector-job"}'


def fake_redis(
    processing_positions=None,
    pending_positions=None,
):
    redis = AsyncMock()

    redis.lpos.side_effect = [
        processing_positions,
        pending_positions,
    ]

    return redis


@pytest.mark.asyncio
async def test_message_in_processing_queue():
    redis = fake_redis([0], [])

    result = await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result == "processing"
    assert redis.lpos.await_count == 2


@pytest.mark.asyncio
async def test_message_in_pending_queue():
    redis = fake_redis([], [2])

    result = await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result == "pending"


@pytest.mark.asyncio
async def test_message_missing_from_both_queues():
    redis = fake_redis([], [])

    result = await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result == "missing"


@pytest.mark.asyncio
async def test_message_in_both_queues_is_ambiguous():
    redis = fake_redis([0], [1])

    result = await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result == "ambiguous"


@pytest.mark.asyncio
async def test_duplicate_processing_messages_are_ambiguous():
    redis = fake_redis([0, 3], [])

    result = await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result == "ambiguous"


@pytest.mark.asyncio
async def test_duplicate_pending_messages_are_ambiguous():
    redis = fake_redis([], [1, 4])

    result = await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    assert result == "ambiguous"


@pytest.mark.asyncio
async def test_missing_message_is_rejected():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="raw message is required",
    ):
        await inspect_reservation(
            redis,
            "",
            processing_key=PROCESSING,
            pending_key=PENDING,
        )

    redis.lpos.assert_not_awaited()


@pytest.mark.asyncio
async def test_identical_queue_keys_are_rejected():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="must differ",
    ):
        await inspect_reservation(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PROCESSING,
        )

    redis.lpos.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_queue_key_is_rejected():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="Both Redis queue keys are required",
    ):
        await inspect_reservation(
            redis,
            RAW,
            processing_key="",
            pending_key=PENDING,
        )

    redis.lpos.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_communication_error_propagates():
    redis = AsyncMock()
    redis.lpos.side_effect = ConnectionError("Redis temporarily unavailable")

    with pytest.raises(ConnectionError):
        await inspect_reservation(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PENDING,
        )


@pytest.mark.asyncio
async def test_exact_raw_message_is_checked():
    redis = fake_redis([0], [])

    await inspect_reservation(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
    )

    redis.lpos.assert_any_await(
        PROCESSING,
        RAW,
        count=0,
    )

    redis.lpos.assert_any_await(
        PENDING,
        RAW,
        count=0,
    )
