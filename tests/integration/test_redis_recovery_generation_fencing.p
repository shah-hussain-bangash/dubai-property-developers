
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
    """Create isolated Redis keys for each test."""

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

    keys = [processing, pending, evidence, fencing]

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
    """Verify the isolated Redis fencing setup."""

    client, processing, pending, evidence, fencing = (
        fenced_redis_setup
    )

    raw = '{"job_id":"fictional-stale-generation"}'

    await client.lpush(processing, raw)
    await client.set(fencing, "2")

    stale_generation = 1

    assert int(await client.get(fencing)) > stale_generation
    assert await client.lrange(processing, 0, -1) == [raw]
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0


async def test_fenced_transition_rejects_stale_generation(
    fenced_redis_setup,
):
    """Reject generation 1 when Redis stores generation 2."""

    client, processing, pending, evidence, fencing = (
        fenced_redis_setup
    )

    raw = '{"job_id":"fictional-fenced-stale"}'

    await client.lpush(processing, raw)
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
    assert await client.lrange(processing, 0, -1) == [raw]
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0
    assert await client.get(fencing) == "2"


async def test_authorized_generation_moves_reservation(
    fenced_redis_setup,
):
    """A matching generation can perform the transition."""

    client, processing, pending, evidence, fencing = (
        fenced_redis_setup
    )

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
    """Repeating the same authorized transition is idempotent."""

    client, processing, pending, evidence, fencing = (
        fenced_redis_setup
    )

    raw = '{"job_id":"fictional-fenced-replay"}'

    await client.lpush(processing, raw)
    await client.set(fencing, "3")

    first = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=3,
    )

    second = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=3,
    )

    assert first == "moved"
    assert second == "already_moved"
    assert await client.llen(processing) == 0
    assert await client.lrange(pending, 0, -1) == [raw]
    assert await client.llen(pending) == 1
    assert await client.get(evidence) == "moved"


async def test_missing_fencing_state_rejects_transition(
    fenced_redis_setup,
):
    """An uninitialized fencing key must deny movement."""

    client, processing, pending, evidence, fencing = (
        fenced_redis_setup
    )

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
    """A stale generation is rejected even if evidence exists."""

    client, processing, pending, evidence, fencing = (
        fenced_redis_setup
    )

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

    # Simulate publication of a newer generation.
    await client.set(fencing, "2")

    stale_result = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=1,
    )

    assert stale_result == "stale"
    assert await client.llen(processing) == 0
    assert await client.lrange(pending, 0, -1) == [raw]
    assert await client.get(evidence) == "moved"
    assert await client.get(fencing) == "2"
