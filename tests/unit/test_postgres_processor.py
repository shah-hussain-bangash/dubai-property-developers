"""Unit tests for authenticated PostgreSQL job processing.

All dependencies are mocked. No PostgreSQL, Redis or Docker access.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.payload_auth import JobPayloadAuthenticationError
from apps.worker.jobs.postgres_processor import process_postgres_job


def make_job():
    return JobEnvelope(
        job_id="fictional-pg-job",
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={"document_id": "fictional-document"},
        max_attempts=3,
    )


def make_store(
    job,
    *,
    status="pending",
    claim_token="test-lease-token",  # noqa: S107 -- Synthetic lease token used only by this test fixture.
    completed=True,
    failure_status="retrying",
):
    record = SimpleNamespace(
        job_type=job.job_type,
        max_attempts=job.max_attempts,
        status=status,
    )

    return SimpleNamespace(
        get=AsyncMock(return_value=record),
        claim=AsyncMock(return_value=claim_token),
        complete=AsyncMock(return_value=completed),
        fail=AsyncMock(return_value=failure_status),
    )


def make_authenticator(job):
    return SimpleNamespace(authenticate=AsyncMock(return_value=job))


@pytest.mark.asyncio
async def test_successful_job_completes_and_acknowledges():
    job = make_job()
    store = make_store(job)
    authenticator = make_authenticator(job)
    handler = AsyncMock(return_value={"ok": True})
    redis = object()
    raw = job.model_dump_json()

    with (
        patch(
            "apps.worker.jobs.postgres_processor.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.jobs.postgres_processor.acknowledge_job",
            new_callable=AsyncMock,
            return_value=True,
        ) as acknowledge,
    ):
        result = await process_postgres_job(
            object(),
            redis,
            raw,
            store,
            authenticator=authenticator,
            worker_id="worker-A",
        )

    assert result == "succeeded"
    authenticator.authenticate.assert_awaited_once()
    handler.assert_awaited_once()
    store.claim.assert_awaited_once()
    store.complete.assert_awaited_once()
    acknowledge.assert_awaited_once_with(redis, raw)


@pytest.mark.asyncio
async def test_completed_duplicate_is_not_executed():
    job = make_job()
    store = make_store(job, status="succeeded")
    authenticator = make_authenticator(job)
    handler = AsyncMock()

    with (
        patch(
            "apps.worker.jobs.postgres_processor.get_handler",
            return_value=handler,
        ),
        patch(
            "apps.worker.jobs.postgres_processor.acknowledge_job",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=authenticator,
            worker_id="worker-B",
        )

    assert result == "duplicate"
    authenticator.authenticate.assert_awaited_once()
    handler.assert_not_awaited()
    store.claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_claim_prevents_duplicate_execution():
    job = make_job()
    store = make_store(
        job,
        status="processing",
        claim_token=None,
    )
    handler = AsyncMock()

    with patch(
        "apps.worker.jobs.postgres_processor.get_handler",
        return_value=handler,
    ):
        result = await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=make_authenticator(job),
            worker_id="worker-B",
        )

    assert result == "deferred"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_retry_is_deferred():
    job = make_job()
    store = make_store(
        job,
        status="retrying",
        claim_token=None,
    )
    handler = AsyncMock()

    with patch(
        "apps.worker.jobs.postgres_processor.get_handler",
        return_value=handler,
    ):
        result = await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=make_authenticator(job),
            worker_id="worker-C",
        )

    assert result == "deferred"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_failure_updates_postgres():
    job = make_job()
    store = make_store(job, failure_status="retrying")
    handler = AsyncMock(side_effect=RuntimeError("Fictional handler failure"))

    with patch(
        "apps.worker.jobs.postgres_processor.get_handler",
        return_value=handler,
    ):
        result = await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=make_authenticator(job),
            worker_id="worker-A",
        )

    assert result == "failed"
    store.fail.assert_awaited_once()
    store.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_lease_prevents_completion():
    job = make_job()
    store = make_store(job, completed=False)
    handler = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "apps.worker.jobs.postgres_processor.get_handler",
            return_value=handler,
        ),
        pytest.raises(
            RuntimeError,
            match="completion lease is no longer valid",
        ),
    ):
        await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=make_authenticator(job),
            worker_id="worker-A",
        )

    store.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_forged_payload_is_rejected_before_claim():
    job = make_job()
    store = make_store(job)
    authenticator = make_authenticator(job)

    authenticator.authenticate.side_effect = JobPayloadAuthenticationError("Forged Redis payload")

    with (
        patch("apps.worker.jobs.postgres_processor.get_handler") as handler_lookup,
        pytest.raises(
            JobPayloadAuthenticationError,
            match="Forged Redis payload",
        ),
    ):
        await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=authenticator,
            worker_id="worker-A",
        )

    store.get.assert_not_awaited()
    store.claim.assert_not_awaited()
    store.complete.assert_not_awaited()
    handler_lookup.assert_not_called()


@pytest.mark.asyncio
async def test_mismatching_authenticated_result_is_rejected():
    job = make_job()
    store = make_store(job)

    different_job = job.model_copy(update={"payload": {"document_id": "other-document"}})

    authenticator = make_authenticator(different_job)

    with (
        patch("apps.worker.jobs.postgres_processor.get_handler") as handler_lookup,
        pytest.raises(
            JobPayloadAuthenticationError,
            match="does not match Redis delivery",
        ),
    ):
        await process_postgres_job(
            object(),
            object(),
            job.model_dump_json(),
            store,
            authenticator=authenticator,
            worker_id="worker-A",
        )

    store.get.assert_not_awaited()
    store.claim.assert_not_awaited()
    handler_lookup.assert_not_called()
