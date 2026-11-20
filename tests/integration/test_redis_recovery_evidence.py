
"""Integration tests for Redis recovery evidence.

These tests use real Redis with isolated test keys.
They do not access PostgreSQL or application job queues.

Run with:
    python -m pytest tests/integration/test_redis_recovery_evidence.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
import redis.asyncio as redis_async

from apps.worker.jobs.redis_recovery_evidence import (
    recovery_evidence_key,
    requeue_with_evidence,
)


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def redis_recovery_setup():
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

    processing = f"test:recovery:{unique_id}:processing"
    pending = f"test:recovery:{unique_id}:pending"

    operation_id = uuid.uuid4()
    evidence = recovery_evidence_key(
        operation_id,
        prefix=f"test:recovery:{unique_id}:evidence",
    )

    keys = [processing, pending, evidence]

    try:
        assert await client.ping() is True
        assert await client.exists(*keys) == 0

        yield client, processing, pending, evidence

    finally:
        await client.delete(*keys)
        await client.aclose()


async def test_real_redis_successful_transition(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    raw = '{"job_id":"test-success"}'

    await client.lpush(processing, raw)

    result = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "moved"
    assert await client.llen(processing) == 0
    assert await client.lrange(pending, 0, -1) == [raw]
    assert await client.get(evidence) == "moved"
    assert await client.ttl(evidence) == -1


async def test_real_redis_repeat_does_not_duplicate(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    raw = '{"job_id":"test-idempotency"}'

    await client.lpush(processing, raw)

    first = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    second = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert first == "moved"
    assert second == "already_moved"
    assert await client.lrange(pending, 0, -1) == [raw]


async def test_real_redis_missing_reservation(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    result = await requeue_with_evidence(
        client,
        '{"job_id":"test-missing"}',
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "missing"
    assert await client.exists(evidence) == 0
    assert await client.llen(pending) == 0


async def test_real_redis_duplicate_processing_is_ambiguous(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    raw = '{"job_id":"test-duplicates"}'

    await client.lpush(processing, raw, raw)

    result = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "ambiguous"
    assert await client.llen(processing) == 2
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0


async def test_real_redis_existing_pending_is_ambiguous(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    raw = '{"job_id":"test-existing-pending"}'

    await client.lpush(processing, raw)
    await client.lpush(pending, raw)

    result = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "ambiguous"
    assert await client.llen(processing) == 1
    assert await client.llen(pending) == 1
    assert await client.exists(evidence) == 0


async def test_real_redis_pending_without_processing_is_ambiguous(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    raw = '{"job_id":"test-only-pending"}'

    await client.lpush(pending, raw)

    result = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "ambiguous"
    assert await client.llen(pending) == 1
    assert await client.exists(evidence) == 0


async def test_real_redis_other_jobs_are_unchanged(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    target = '{"job_id":"target"}'
    other = '{"job_id":"other"}'

    await client.lpush(processing, other, target)

    result = await requeue_with_evidence(
        client,
        target,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "moved"
    assert await client.lrange(processing, 0, -1) == [other]
    assert await client.lrange(pending, 0, -1) == [target]


async def test_real_redis_existing_evidence_prevents_second_move(
    redis_recovery_setup,
):
    client, processing, pending, evidence = (
        redis_recovery_setup
    )

    raw = '{"job_id":"test-evidence-first"}'

    await client.set(evidence, "moved")
    await client.lpush(processing, raw)

    result = await requeue_with_evidence(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )

    assert result == "already_moved"
    assert await client.llen(processing) == 1
    assert await client.llen(pending) == 0
