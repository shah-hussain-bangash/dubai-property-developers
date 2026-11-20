
"""Unit tests for guarded recovery transition input validation.

Uses mocked dependencies. Does not connect to PostgreSQL or Redis.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.guarded_recovery_transition import (
    GuardedRecoveryTransition,
)


@pytest.fixture
def guarded():
    return GuardedRecoveryTransition(MagicMock())


@pytest.fixture
def job():
    return JobEnvelope(
        job_id="fictional-guarded-job",
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={},
        max_attempts=3,
    )


def valid_params(job):
    return {
        "redis": AsyncMock(),
        "job": job,
        "raw": job.model_dump_json(),
        "operation_id": uuid.uuid4(),
        "worker_id": "coordinator-A",
        "lease_token": "fictional-lease-token",
        "processing_key": "test:guarded:processing",
        "pending_key": "test:guarded:pending",
    }


@pytest.mark.asyncio
async def test_missing_job_is_rejected(guarded, job):
    params = valid_params(job)
    params["job"] = None

    with pytest.raises(ValueError, match="JobEnvelope is required"):
        await guarded.requeue(**params)

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["", None, 123])
async def test_invalid_raw_is_rejected(guarded, job, raw):
    params = valid_params(job)
    params["raw"] = raw

    with pytest.raises(ValueError, match="Raw Redis message is required"):
        await guarded.requeue(**params)

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_operation_id_is_rejected(guarded, job):
    params = valid_params(job)
    params["operation_id"] = "not-a-uuid"

    with pytest.raises(ValueError, match="Valid operation_id is required"):
        await guarded.requeue(**params)

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_id", ["", " ", None])
async def test_invalid_worker_is_rejected(
    guarded,
    job,
    worker_id,
):
    params = valid_params(job)
    params["worker_id"] = worker_id

    with pytest.raises(ValueError, match="worker_id is required"):
        await guarded.requeue(**params)

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", " ", None])
async def test_invalid_lease_token_is_rejected(
    guarded,
    job,
    token,
):
    params = valid_params(job)
    params["lease_token"] = token

    with pytest.raises(ValueError, match="lease_token is required"):
        await guarded.requeue(**params)

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timeout",
    [0, -1, True, None, "5"],
)
async def test_invalid_redis_timeout_is_rejected(
    guarded,
    job,
    timeout,
):
    params = valid_params(job)
    params["redis_timeout_seconds"] = timeout

    with pytest.raises(
        ValueError,
        match="redis_timeout_seconds must be positive",
    ):
        await guarded.requeue(**params)

    guarded.session_factory.assert_not_called()
