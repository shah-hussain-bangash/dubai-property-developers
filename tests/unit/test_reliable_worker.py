
"""Unit tests for reliable Redis worker processing.

These tests use mocked queue operations.
They do not modify the real Redis server.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.main import process_one


@pytest.mark.asyncio
async def test_successful_job_is_acknowledged():
    """Successful handlers must acknowledge their reservation."""

    job = JobEnvelope(
        job_type="test.success",
        tenant_id="demo-org",
    )
    raw = job.model_dump_json()

    redis = object()
    runtime = object()

    handler = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "apps.worker.main.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.main.acknowledge_job",
            new_callable=AsyncMock,
            return_value=True,
        ) as acknowledge,
        patch(
            "apps.worker.main.transition_job",
            new_callable=AsyncMock,
        ) as transition,
    ):
        result = await process_one(runtime, raw, redis)

    assert result == {"ok": True}
    handler.assert_awaited_once()
    acknowledge.assert_awaited_once_with(redis, raw)
    transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_job_is_retried():
    """Failed jobs should increment attempts and enter retry routing."""

    job = JobEnvelope(
        job_type="test.failure",
        tenant_id="demo-org",
        attempts=0,
        max_attempts=3,
    )
    raw = job.model_dump_json()

    handler = AsyncMock(side_effect=RuntimeError("Test failure"))

    with (
        patch(
            "apps.worker.main.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.main.transition_job",
            new_callable=AsyncMock,
            return_value=True,
        ) as transition,
        patch(
            "apps.worker.main.acknowledge_job",
            new_callable=AsyncMock,
        ) as acknowledge,
    ):
        result = await process_one(object(), raw, object())

    assert result is None
    acknowledge.assert_not_awaited()
    transition.assert_awaited_once()

    args, kwargs = transition.await_args
    updated_job = args[2]

    assert updated_job.job_id == job.job_id
    assert updated_job.attempts == 1
    assert kwargs["dead_letter"] is False


@pytest.mark.asyncio
async def test_exhausted_job_goes_to_dead_letter():
    """Jobs exhausting their attempts must go to the dead-letter queue."""

    job = JobEnvelope(
        job_type="test.failure",
        tenant_id="demo-org",
        attempts=2,
        max_attempts=3,
    )
    raw = job.model_dump_json()

    handler = AsyncMock(side_effect=RuntimeError("Test failure"))

    with (
        patch(
            "apps.worker.main.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.main.transition_job",
            new_callable=AsyncMock,
            return_value=True,
        ) as transition,
    ):
        result = await process_one(object(), raw, object())

    assert result is None
    transition.assert_awaited_once()

    args, kwargs = transition.await_args

    assert args[2].attempts == 3
    assert kwargs["dead_letter"] is True


@pytest.mark.asyncio
async def test_malformed_job_goes_to_dead_letter():
    """Invalid JSON must be routed to dead-letter storage."""

    raw = "{invalid-json"

    with patch(
        "apps.worker.main.transition_job",
        new_callable=AsyncMock,
        return_value=True,
    ) as transition:
        result = await process_one(object(), raw, object())

    assert result is None
    transition.assert_awaited_once()

    args, kwargs = transition.await_args

    assert args[1] == raw
    assert args[2] == raw
    assert kwargs["dead_letter"] is True


@pytest.mark.asyncio
async def test_missing_reservation_is_not_silently_ignored():
    """A missing Redis reservation must raise an error."""

    job = JobEnvelope(
        job_type="test.success",
        tenant_id="demo-org",
    )
    raw = job.model_dump_json()

    handler = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "apps.worker.main.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.main.acknowledge_job",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="reservation was not found",
        ):
            await process_one(object(), raw, object())
