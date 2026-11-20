"""Unit tests for PostgreSQL-to-Redis outbox dispatching.

All external components are mocked.
These tests do not access PostgreSQL, Redis, or Docker.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.outbox.dispatcher import OutboxDispatcher
from database.repositories.postgres_outbox_dispatch_store import (
    ClaimedOutboxMessage,
)


def make_dispatcher(
    *,
    claimed=None,
    acknowledged=True,
    failed_recorded=True,
):
    """Create a dispatcher with correctly mocked dependencies."""

    organization_id = uuid.uuid4()

    job = JobEnvelope(
        job_id="fictional-dispatch-job",
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={"document_id": "fictional-document"},
    )

    if claimed is None:
        claimed = ClaimedOutboxMessage(
            organization_id=organization_id,
            job_id=job.job_id,
            payload_ciphertext=b"fictional-encrypted-payload",
            encryption_key_id="test-key",
            lease_token="fictional-lease-token",
            publish_attempts=1,
        )

    store = SimpleNamespace(
        claim_next=AsyncMock(return_value=claimed),
        mark_published=AsyncMock(return_value=acknowledged),
        mark_failed=AsyncMock(return_value=failed_recorded),
    )

    # IMPORTANT:
    # Encryption/decryption methods are synchronous.
    # Use Mock, not AsyncMock.
    cipher = SimpleNamespace(decrypt=Mock(return_value=job))

    redis = SimpleNamespace()

    dispatcher = OutboxDispatcher(
        dispatch_store=store,
        session_factory=None,
        cipher=cipher,
        redis=redis,
        worker_id="test-dispatcher",
    )

    return dispatcher, store, cipher, job


@pytest.mark.asyncio
async def test_idle_dispatcher_does_not_publish():
    dispatcher, store, _, _ = make_dispatcher()

    store.claim_next.return_value = None

    with patch.object(
        dispatcher,
        "_tenant_slug",
        new_callable=AsyncMock,
    ) as tenant_lookup:
        result = await dispatcher.dispatch_once()

    assert result == "idle"
    tenant_lookup.assert_not_awaited()
    store.mark_published.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_dispatch_publishes_and_acknowledges():
    dispatcher, store, cipher, job = make_dispatcher()

    with (
        patch.object(
            dispatcher,
            "_tenant_slug",
            new_callable=AsyncMock,
            return_value="demo-org",
        ),
        patch(
            "apps.worker.outbox.dispatcher.enqueue",
            new_callable=AsyncMock,
            return_value=job.job_id,
        ) as enqueue_mock,
    ):
        result = await dispatcher.dispatch_once()

    assert result == "published"

    enqueue_mock.assert_awaited_once_with(
        dispatcher.redis,
        job,
    )

    cipher.decrypt.assert_called_once()
    store.mark_published.assert_awaited_once()
    store.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_failure_schedules_retry():
    dispatcher, store, _, _ = make_dispatcher()

    with (
        patch.object(
            dispatcher,
            "_tenant_slug",
            new_callable=AsyncMock,
            return_value="demo-org",
        ),
        patch(
            "apps.worker.outbox.dispatcher.enqueue",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis unavailable"),
        ),
    ):
        result = await dispatcher.dispatch_once()

    assert result == "retrying"

    store.mark_failed.assert_awaited_once()
    store.mark_published.assert_not_awaited()


@pytest.mark.asyncio
async def test_decryption_failure_does_not_publish():
    dispatcher, store, cipher, _ = make_dispatcher()

    cipher.decrypt.side_effect = ValueError("Invalid encrypted envelope")

    with (
        patch.object(
            dispatcher,
            "_tenant_slug",
            new_callable=AsyncMock,
            return_value="demo-org",
        ),
        patch(
            "apps.worker.outbox.dispatcher.enqueue",
            new_callable=AsyncMock,
        ) as enqueue_mock,
    ):
        result = await dispatcher.dispatch_once()

    assert result == "retrying"

    enqueue_mock.assert_not_awaited()
    store.mark_failed.assert_awaited_once()
    store.mark_published.assert_not_awaited()


@pytest.mark.asyncio
async def test_acknowledgement_failure_is_reported():
    dispatcher, store, _, job = make_dispatcher(
        acknowledged=False,
    )

    with (
        patch.object(
            dispatcher,
            "_tenant_slug",
            new_callable=AsyncMock,
            return_value="demo-org",
        ),
        patch(
            "apps.worker.outbox.dispatcher.enqueue",
            new_callable=AsyncMock,
            return_value=job.job_id,
        ),
        pytest.raises(
            RuntimeError,
            match="duplicate delivery is possible",
        ),
    ):
        await dispatcher.dispatch_once()

    store.mark_published.assert_awaited_once()


@pytest.mark.asyncio
async def test_failure_recording_rejection_is_reported():
    dispatcher, store, _, _ = make_dispatcher(
        failed_recorded=False,
    )

    with (
        patch.object(
            dispatcher,
            "_tenant_slug",
            new_callable=AsyncMock,
            return_value="demo-org",
        ),
        patch(
            "apps.worker.outbox.dispatcher.enqueue",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis unavailable"),
        ),
        pytest.raises(
            RuntimeError,
            match="failure could not be recorded",
        ),
    ):
        await dispatcher.dispatch_once()

    store.mark_failed.assert_awaited_once()
