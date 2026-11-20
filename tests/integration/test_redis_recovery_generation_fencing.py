"""Integration tests for Redis recovery generation fencing.

Development-only prototype tests.

Uses real Redis with isolated test keys.
Does not access PostgreSQL or application job queues.

Run with RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os
import uuid

import pytest
import redis.asyncio as redis_async

from apps.worker.jobs.redis_recovery_fenced import (
    requeue_with_fencing,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration tests disabled",
    ),
]


@pytest.fixture
async def fenced_redis_setup():
    """Create an isolated Redis client and unique test keys."""

    redis_url = os.getenv(
        "TEST_REDIS_URL",
        "redis://127.0.0.1:6379/0",
    )

    client = redis_async.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    unique_id = uuid.uuid4().hex
    prefix = f"test:recovery:fencing:{unique_id}"

    processing = f"{prefix}:processing"
    pending = f"{prefix}:pending"
    evidence = f"{prefix}:evidence"
    fencing = f"{prefix}:fencing"

    keys = [
        processing,
        pending,
        evidence,
        fencing,
    ]

    try:
        assert await client.ping() is True
        assert await client.exists(*keys) == 0

        yield client, processing, pending, evidence, fencing

    finally:
        await client.delete(*keys)
        await client.aclose()


async def test_stale_generation_cannot_move_reservation(
    fenced_redis_setup,
):
    """Verify the isolated Redis fencing test setup."""

    client, processing, pending, evidence, fencing = fenced_redis_setup

    raw = '{"job_id":"fictional-stale-generation"}'

    await client.lpush(processing, raw)

    # Simulate a newer coordinator authorized in Redis.
    await client.set(fencing, "2")

    # An earlier coordinator still holds generation 1.
    stale_generation = 1

    assert int(await client.get(fencing)) > stale_generation

    # The test setup must not modify recovery queues.
    assert await client.lrange(processing, 0, -1) == [raw]
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0


async def test_fenced_transition_rejects_stale_generation(
    fenced_redis_setup,
):
    """Reject generation 1 when Redis stores generation 2."""

    client, processing, pending, evidence, fencing = fenced_redis_setup

    raw = '{"job_id":"fictional-fenced-stale"}'

    # Simulate an existing processing reservation.
    await client.lpush(processing, raw)

    # Coordinator B's generation is stored in Redis.
    await client.set(fencing, "2")

    # Coordinator A attempts recovery with stale generation 1.
    result = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=1,
    )

    # Redis must reject the stale generation.
    assert result == "stale"

    # Rejection must leave the reservation unchanged.
    assert await client.lrange(processing, 0, -1) == [raw]
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0

    # The authorized generation remains unchanged.
    assert await client.get(fencing) == "2"


async def test_authorized_generation_moves_reservation(
    fenced_redis_setup,
):
    """Matching generation moves exactly one reservation."""
    client, processing, pending, evidence, fencing = fenced_redis_setup
    raw = '{"job_id":"fictional-authorized-generation"}'

    await client.lpush(processing, raw)
    await client.set(fencing, "2")

    result = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=2,
    )

    assert result == "moved"
    assert await client.llen(processing) == 0
    assert await client.lrange(pending, 0, -1) == [raw]
    assert await client.get(evidence) == "moved"
    assert await client.get(fencing) == "2"


async def test_authorized_replay_does_not_duplicate(
    fenced_redis_setup,
):
    """Repeating an authorized operation does not duplicate a job."""
    client, processing, pending, evidence, fencing = fenced_redis_setup
    raw = '{"job_id":"fictional-fenced-replay"}'

    await client.lpush(processing, raw)
    await client.set(fencing, "3")

    async def invoke():
        return await requeue_with_fencing(
            client,
            raw,
            processing_key=processing,
            pending_key=pending,
            evidence_key=evidence,
            fencing_key=fencing,
            generation=3,
        )

    first = await invoke()
    second = await invoke()

    assert first == "moved"
    assert second == "already_moved"
    assert await client.llen(processing) == 0
    assert await client.lrange(pending, 0, -1) == [raw]
    assert await client.llen(pending) == 1
    assert await client.get(evidence) == "moved"


async def test_missing_fencing_state_rejects_transition(
    fenced_redis_setup,
):
    """Missing fencing state must prevent queue movement."""
    client, processing, pending, evidence, fencing = fenced_redis_setup
    raw = '{"job_id":"fictional-uninitialized-fencing"}'

    await client.lpush(processing, raw)
    assert await client.exists(fencing) == 0

    result = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=1,
    )

    assert result == "uninitialized"
    assert await client.lrange(processing, 0, -1) == [raw]
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0


async def test_stale_replay_cannot_bypass_fencing(
    fenced_redis_setup,
):
    """Stale ownership is rejected even with existing evidence."""
    client, processing, pending, evidence, fencing = fenced_redis_setup
    raw = '{"job_id":"fictional-stale-replay"}'

    await client.lpush(processing, raw)
    await client.set(fencing, "1")

    first = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=1,
    )

    assert first == "moved"

    # Simulate an updated Redis generation.
    await client.set(fencing, "2")

    result = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=1,
    )

    assert result == "stale"
    assert await client.llen(processing) == 0
    assert await client.lrange(pending, 0, -1) == [raw]
    assert await client.get(evidence) == "moved"
    assert await client.get(fencing) == "2"
