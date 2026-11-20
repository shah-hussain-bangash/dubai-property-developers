"""Unit tests for guarded recovery raw-message validation.

These tests use mocked dependencies and do not access
PostgreSQL, Redis, or the running Docker worker.
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
def job():
    return JobEnvelope(
        job_id="fictional-raw-validation",
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={"test": "original"},
        max_attempts=3,
    )


@pytest.fixture
def guarded():
    return GuardedRecoveryTransition(MagicMock())


async def invoke(guarded, job, raw):
    return await guarded.requeue(
        redis=AsyncMock(),
        job=job,
        raw=raw,
        operation_id=uuid.uuid4(),
        worker_id="test-coordinator",
        lease_token="test-lease",
        processing_key="test:raw:processing",
        pending_key="test:raw:pending",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "{invalid}",
        "[]",
        "{}",
        '{"job_id":"missing-required-fields"}',
    ],
)
async def test_malformed_envelope_is_rejected(
    guarded,
    job,
    raw,
):
    with pytest.raises(
        ValueError,
        match="Raw Redis message is not a valid JobEnvelope",
    ):
        await invoke(guarded, job, raw)

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_different_job_id_is_rejected(guarded, job):
    modified = job.model_copy(update={"job_id": "different-job-id"})

    with pytest.raises(
        ValueError,
        match="Raw Redis message does not match authorized job",
    ):
        await invoke(
            guarded,
            job,
            modified.model_dump_json(),
        )

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_different_payload_is_rejected(guarded, job):
    modified = job.model_copy(update={"payload": {"test": "tampered"}})

    with pytest.raises(
        ValueError,
        match="Raw Redis message does not match authorized job",
    ):
        await invoke(
            guarded,
            job,
            modified.model_dump_json(),
        )

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_different_tenant_is_rejected(guarded, job):
    modified = job.model_copy(update={"tenant_id": "other-tenant"})

    with pytest.raises(
        ValueError,
        match="Raw Redis message does not match authorized job",
    ):
        await invoke(
            guarded,
            job,
            modified.model_dump_json(),
        )

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_different_max_attempts_is_rejected(guarded, job):
    modified = job.model_copy(update={"max_attempts": 99})

    with pytest.raises(
        ValueError,
        match="Raw Redis message does not match authorized job",
    ):
        await invoke(
            guarded,
            job,
            modified.model_dump_json(),
        )

    guarded.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_different_attempts_is_rejected(guarded, job):
    modified = job.model_copy(update={"attempts": 2})

    with pytest.raises(
        ValueError,
        match="Raw Redis message does not match authorized job",
    ):
        await invoke(
            guarded,
            job,
            modified.model_dump_json(),
        )

    guarded.session_factory.assert_not_called()
