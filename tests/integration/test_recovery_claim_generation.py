
"""Integration tests for generation-aware PostgreSQL recovery claims.

Development-only. Uses fictional PostgreSQL jobs and the existing
recovery_setup fixture. Does not access Redis or execute handlers.

Run with RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from database.models.job_recovery_operation import JobRecoveryOperation
from database.repositories.postgres_recovery_lease_store import (
    RecoveryLeaseClaim,
)
from tests.integration.test_postgres_recovery_lease_store import (
    create_operation,
    get_operation,
    recovery_setup,
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL integration tests disabled",
    ),
]


async def test_first_claim_returns_generation_one(recovery_setup):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(
        jobs, recovery, factory, ids
    )

    result = await leases.claim_with_generation(
        "demo-org",
        operation_id,
        "generation-coordinator-A",
    )

    assert isinstance(result, RecoveryLeaseClaim)
    assert result.lease_token
    assert result.generation == 1

    saved = await get_operation(factory, operation_id)

    assert saved.status == "processing"
    assert saved.worker_id == "generation-coordinator-A"
    assert saved.lease_token == result.lease_token
    assert saved.attempts == result.generation


async def test_active_lease_cannot_be_claimed_again(recovery_setup):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(
        jobs, recovery, factory, ids
    )

    first = await leases.claim_with_generation(
        "demo-org",
        operation_id,
        "generation-coordinator-A",
    )

    assert first is not None

    second = await leases.claim_with_generation(
        "demo-org",
        operation_id,
        "generation-coordinator-B",
    )

    assert second is None

    saved = await get_operation(factory, operation_id)

    assert saved.worker_id == "generation-coordinator-A"
    assert saved.lease_token == first.lease_token
    assert saved.attempts == 1


async def test_expired_lease_increases_generation(recovery_setup):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(
        jobs, recovery, factory, ids
    )

    first = await leases.claim_with_generation(
        "demo-org",
        operation_id,
        "generation-coordinator-A",
    )

    assert first is not None
    assert first.generation == 1

    # Expire only this fictional test operation's lease.
    async with factory() as session:
        async with session.begin():
            await session.execute(
                update(JobRecoveryOperation)
                .where(JobRecoveryOperation.id == operation_id)
                .values(
                    lease_expires_at=(
                        datetime.now(UTC) - timedelta(minutes=5)
                    )
                )
            )

    second = await leases.claim_with_generation(
        "demo-org",
        operation_id,
        "generation-coordinator-B",
    )

    assert second is not None
    assert second.generation == first.generation + 1
    assert second.lease_token != first.lease_token

    saved = await get_operation(factory, operation_id)

    assert saved.worker_id == "generation-coordinator-B"
    assert saved.lease_token == second.lease_token
    assert saved.attempts == second.generation


async def test_legacy_claim_still_returns_string_token(recovery_setup):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(
        jobs, recovery, factory, ids
    )

    token = await leases.claim(
        "demo-org",
        operation_id,
        "legacy-coordinator",
    )

    assert isinstance(token, str)
    assert token

    saved = await get_operation(factory, operation_id)

    assert saved.lease_token == token
    assert saved.attempts == 1


async def test_wrong_tenant_receives_no_generation(recovery_setup):
    jobs, recovery, leases, factory, ids = recovery_setup

    operation_id = await create_operation(
        jobs, recovery, factory, ids
    )

    result = await leases.claim_with_generation(
        "nonexistent-generation-tenant",
        operation_id,
        "generation-coordinator",
    )

    assert result is None

    saved = await get_operation(factory, operation_id)

    assert saved.attempts == 0
    assert saved.status == "pending"
