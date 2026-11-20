
"""Demonstrate the PostgreSQL-to-Redis fencing publication gap.

Development-only integration test.

Uses real PostgreSQL and isolated local Redis keys.
Does not modify application queues or execute job handlers.

This is an expected-failure safety test until a complete
cross-system fencing protocol is implemented.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from apps.worker.jobs.redis_recovery_fenced import (
    requeue_with_fencing,
)
from database.models.job_recovery_operation import (
    JobRecoveryOperation,
)
from tests.integration.test_guarded_recovery_real_redis import (
    TENANT,
    create_case,
    environment,
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration tests disabled",
    ),
]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known cross-system gap: PostgreSQL ownership can advance "
        "before Redis receives the newer fencing generation"
    ),
)
async def test_old_generation_cannot_move_after_postgres_takeover(
    environment,
):
    case = await create_case(environment)

    client = environment["redis"]
    factory = environment["factory"]
    leases = environment["leases"]

    operation_id = case["operation_id"]
    raw = case["raw"]

    processing = case["processing_key"]
    pending = case["pending_key"]
    evidence = case["evidence_key"]

    fencing = processing + ":fencing"

    environment["redis_keys"].append(fencing)

    # Original claim from create_case() is generation 1.
    await client.lpush(processing, raw)
    await client.set(fencing, "1")

    # Expire this fictional operation's PostgreSQL lease.
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

    # Coordinator B takes over and receives generation 2.
    takeover = await leases.claim_with_generation(
        TENANT,
        operation_id,
        "publication-gap-coordinator-B",
    )

    assert takeover is not None
    assert takeover.generation == 2

    # Deliberately leave Redis at the stale generation.
    assert await client.get(fencing) == "1"

    # Coordinator A sends its delayed generation-1 command.
    result = await requeue_with_fencing(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
        fencing_key=fencing,
        generation=1,
    )

    # Required safety property: old ownership must not move.
    # Current prototype violates this until publication is safe.
    assert result == "stale"

    assert await client.lrange(processing, 0, -1) == [raw]
    assert await client.llen(pending) == 0
    assert await client.exists(evidence) == 0
