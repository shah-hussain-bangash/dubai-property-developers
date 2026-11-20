"""Safety regression tests for Redis recovery lease fencing.

Development-only. Uses a mocked Redis client.

The xfail test documents a known gap:
a stale coordinator can still call the Redis recovery transition
after its PostgreSQL lease has expired.

It must be converted to a passing safety test before automatic
Redis recovery is enabled.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.redis_recovery_evidence import (
    requeue_with_evidence,
)

RAW = '{"job_id":"fictional-fencing-test"}'
PROCESSING = "test:fencing:processing"
PENDING = "test:fencing:pending"
EVIDENCE = "test:fencing:evidence"


@pytest.mark.asyncio
async def test_redis_error_does_not_report_success():
    redis = AsyncMock()
    redis.eval.side_effect = ConnectionError("Redis unavailable")

    with pytest.raises(ConnectionError):
        await requeue_with_evidence(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PENDING,
            evidence_key=EVIDENCE,
        )


@pytest.mark.asyncio
async def test_missing_reservation_does_not_report_success():
    redis = AsyncMock()
    redis.eval.return_value = 0

    result = await requeue_with_evidence(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
        evidence_key=EVIDENCE,
    )

    assert result == "missing"


@pytest.mark.asyncio
async def test_ambiguous_reservation_does_not_report_success():
    redis = AsyncMock()
    redis.eval.return_value = 3

    result = await requeue_with_evidence(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
        evidence_key=EVIDENCE,
    )

    assert result == "ambiguous"


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=("Known gap: Redis transition does not enforce PostgreSQL recovery lease fencing"),
)
async def test_stale_coordinator_cannot_mutate_redis():
    """Document the missing stale-coordinator safeguard."""

    redis = AsyncMock()
    redis.eval.return_value = 1

    lease_is_valid = False

    if lease_is_valid:
        pytest.fail("Test setup must simulate an expired lease")

    result = await requeue_with_evidence(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
        evidence_key=EVIDENCE,
    )

    # This assertion deliberately fails with the current interface.
    # A future fenced transition must reject stale ownership.
    assert result != "moved"
