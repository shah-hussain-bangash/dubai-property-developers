"""Unit tests for atomic Redis recovery evidence.

These tests mock Redis and do not modify real queues or databases.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from apps.worker.jobs.redis_recovery_evidence import (
    RECOVERY_EVIDENCE_SCRIPT,
    recovery_evidence_key,
    requeue_with_evidence,
)

PROCESSING = "test:recovery:processing"
PENDING = "test:recovery:pending"
EVIDENCE = "test:recovery:evidence"
RAW = '{"job_id":"fictional-evidence-job"}'


def make_redis(result: int) -> AsyncMock:
    redis = AsyncMock()
    redis.eval.return_value = result
    return redis


async def invoke(redis: AsyncMock, **kwargs):
    return await requeue_with_evidence(
        redis,
        RAW,
        processing_key=PROCESSING,
        pending_key=PENDING,
        evidence_key=EVIDENCE,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_successful_requeue_records_evidence():
    redis = make_redis(1)

    assert await invoke(redis) == "moved"

    redis.eval.assert_awaited_once_with(
        RECOVERY_EVIDENCE_SCRIPT,
        3,
        PROCESSING,
        PENDING,
        EVIDENCE,
        RAW,
    )


@pytest.mark.asyncio
async def test_existing_evidence_prevents_requeue():
    redis = make_redis(2)

    assert await invoke(redis) == "already_moved"


@pytest.mark.asyncio
async def test_missing_reservation_returns_missing():
    redis = make_redis(0)

    assert await invoke(redis) == "missing"


@pytest.mark.asyncio
async def test_ambiguous_reservation_is_rejected():
    redis = make_redis(3)

    assert await invoke(redis) == "ambiguous"


@pytest.mark.asyncio
@pytest.mark.parametrize("unexpected", [4, -1, "unknown", None])
async def test_unexpected_redis_result_is_rejected(unexpected):
    redis = AsyncMock()
    redis.eval.return_value = unexpected

    with pytest.raises(
        RuntimeError,
        match="Unexpected Redis recovery transition result",
    ):
        await invoke(redis)


@pytest.mark.asyncio
async def test_empty_raw_message_is_rejected():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="raw message is required",
    ):
        await requeue_with_evidence(
            redis,
            "",
            processing_key=PROCESSING,
            pending_key=PENDING,
            evidence_key=EVIDENCE,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_identical_queue_keys_are_rejected():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="Redis keys must be distinct",
    ):
        await requeue_with_evidence(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PROCESSING,
            evidence_key=EVIDENCE,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_evidence_key_matching_queue_is_rejected():
    redis = AsyncMock()

    with pytest.raises(
        ValueError,
        match="Redis keys must be distinct",
    ):
        await requeue_with_evidence(
            redis,
            RAW,
            processing_key=PROCESSING,
            pending_key=PENDING,
            evidence_key=PENDING,
        )

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"processing_key": ""},
        {"pending_key": ""},
        {"evidence_key": ""},
        {"processing_key": None},
        {"pending_key": None},
        {"evidence_key": None},
    ],
)
async def test_invalid_keys_are_rejected(overrides):
    redis = AsyncMock()

    params = {
        "processing_key": PROCESSING,
        "pending_key": PENDING,
        "evidence_key": EVIDENCE,
    }
    params.update(overrides)

    with pytest.raises(
        ValueError,
        match="All Redis keys are required",
    ):
        await requeue_with_evidence(redis, RAW, **params)

    redis.eval.assert_not_awaited()


def test_evidence_key_uses_operation_uuid():
    operation_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

    assert recovery_evidence_key(operation_id) == (
        "recovery:evidence:12345678123456781234567812345678"
    )


def test_evidence_key_supports_custom_prefix():
    operation_id = uuid.uuid4()

    assert (
        recovery_evidence_key(
            operation_id,
            prefix="test:evidence",
        )
        == f"test:evidence:{operation_id.hex}"
    )


def test_evidence_key_rejects_invalid_uuid():
    with pytest.raises(
        ValueError,
        match="operation_id must be a UUID",
    ):
        recovery_evidence_key("not-a-uuid")


@pytest.mark.parametrize("prefix", ["", " ", None])
def test_evidence_key_rejects_invalid_prefix(prefix):
    with pytest.raises(ValueError, match="prefix is required"):
        recovery_evidence_key(
            uuid.uuid4(),
            prefix=prefix,
        )


@pytest.mark.asyncio
async def test_redis_communication_error_propagates():
    redis = AsyncMock()
    redis.eval.side_effect = ConnectionError("Redis temporarily unavailable")

    with pytest.raises(ConnectionError):
        await invoke(redis)


def test_script_has_no_expiring_evidence_marker():
    assert "tonumber(ARGV[2])" not in RECOVERY_EVIDENCE_SCRIPT
    assert "'EX'" not in RECOVERY_EVIDENCE_SCRIPT


def test_script_checks_both_queues_before_removing_message():
    assert "LRANGE" in RECOVERY_EVIDENCE_SCRIPT
    assert "LREM" in RECOVERY_EVIDENCE_SCRIPT
    assert "LPUSH" in RECOVERY_EVIDENCE_SCRIPT
