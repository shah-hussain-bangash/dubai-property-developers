
"""Unit tests for recovery coordinator input authorization.

No PostgreSQL or Redis connections are required.
These tests verify that invalid inputs are rejected before
a database session is opened.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.postgres_redis_recovery_coordinator import (
    PostgresRedisRecoveryCoordinator,
    RecoveryAuthorizationError,
)


@pytest.fixture
def coordinator():
    session_factory = MagicMock()
    return PostgresRedisRecoveryCoordinator(session_factory)


@pytest.fixture
def job():
    return JobEnvelope(
        job_id="fictional-recovery-test",
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={},
        max_attempts=3,
    )


@pytest.mark.asyncio
async def test_invalid_job_is_rejected(coordinator):
    with pytest.raises(
        RecoveryAuthorizationError,
        match="Authenticated JobEnvelope is required",
    ):
        await coordinator.authorize(
            job=None,
            operation_id=uuid.uuid4(),
            worker_id="coordinator-A",
            lease_token="example-token",
        )

    coordinator.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_operation_uuid_is_rejected(
    coordinator,
    job,
):
    with pytest.raises(
        RecoveryAuthorizationError,
        match="Valid operation UUID is required",
    ):
        await coordinator.authorize(
            job=job,
            operation_id="invalid-operation-id",
            worker_id="coordinator-A",
            lease_token="example-token",
        )

    coordinator.session_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_worker",
    ["", " ", None],
)
async def test_invalid_worker_id_is_rejected(
    coordinator,
    job,
    invalid_worker,
):
    with pytest.raises(
        RecoveryAuthorizationError,
        match="worker_id is required",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=uuid.uuid4(),
            worker_id=invalid_worker,
            lease_token="example-token",
        )

    coordinator.session_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_token",
    ["", " ", None],
)
async def test_invalid_lease_token_is_rejected(
    coordinator,
    job,
    invalid_token,
):
    with pytest.raises(
        RecoveryAuthorizationError,
        match="lease_token is required",
    ):
        await coordinator.authorize(
            job=job,
            operation_id=uuid.uuid4(),
            worker_id="coordinator-A",
            lease_token=invalid_token,
        )

    coordinator.session_factory.assert_not_called()
