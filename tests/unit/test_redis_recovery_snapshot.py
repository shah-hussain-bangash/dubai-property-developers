"""Unit tests for the atomic Redis recovery snapshot.

Uses mocked Redis. Does not access real queues or databases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.redis_recovery_snapshot import (
    RECOVERY_SNAPSHOT_SCRIPT,
    inspect_recovery_snapshot,
)

PROCESSING = "test:snapshot:processing"
PENDING = "test:snapshot:pending"
EVIDENCE = "test:snapshot:evidence"
RAW = '{"job_id":"fictional-snapshot-job"}'


def make_redis(result):
    redis = AsyncMock()
    redis.eval.return_value = result
    return redis


async def invoke(redis):
    return await inspect_recovery_snapshot(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
        evidence_key=EVIDENCE,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("redis_result", "expected"),
    [
        (0, "processing"),
        (1, "pending"),
        (2, "missing"),
        (3, "ambiguous"),
        (4, "evidence_present"),
        (5, "uncertain"),
    ],
)
async def test_snapshot_result_mapping(redis_result, expected):
    redis = make_redis(redis_result)

    assert await invoke(redis) == expected

    redis.eval.assert_awaited_once_with(
        RECOVERY_SNAPSHOT_SCRIPT,
        3,
        PROCESSING,
        PENDING,
        EVIDENCE,
        RAW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_result",
    [-1, 6, "invalid", None],
)
async def test_invalid_redis_result_is_rejected(invalid_result):
    redis = make_redis(invalid_result)

    with pytest.raises(
        RuntimeError,
        match="Unexpected Redis recovery snapshot result",
    ):
        await invoke(redis)


@pytest.mark.asyncio
async def test_empty_raw_is_rejected():
    redis = AsyncMock()

    with pytest.raises(ValueError, match="raw message"):
        await inspect_recovery_snapshot(
            redis,
            "",
            processing_key=PROCESSING,
            pending_key=PENDING,
            evidence_key=EVIDENCE,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_key_is_rejected():
    redis = AsyncMock()

    with pytest.raises(ValueError, match="All Redis keys"):
        await inspect_recovery_snapshot(
            redis,
            RAW,
            processing_key="",
            pending_key=PENDING,
            evidence_key=EVIDENCE,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_keys_are_rejected():
    redis = AsyncMock()

    with pytest.raises(ValueError, match="must be distinct"):
        await inspect_recovery_snapshot(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PROCESSING,
            evidence_key=EVIDENCE,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_error_propagates():
    redis = AsyncMock()
    redis.eval.side_effect = ConnectionError("Redis unavailable")

    with pytest.raises(ConnectionError):
        await invoke(redis)


@pytest.mark.asyncio
async def test_inspector_uses_read_only_lua():
    redis = make_redis(0)

    assert await invoke(redis) == "processing"

    assert "LRANGE" in RECOVERY_SNAPSHOT_SCRIPT
    assert "GET" in RECOVERY_SNAPSHOT_SCRIPT

    redis.set.assert_not_awaited()
    redis.delete.assert_not_awaited()
    redis.lrem.assert_not_awaited()
    redis.lpush.assert_not_awaited()
