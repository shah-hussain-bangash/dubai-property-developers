
"""Real Redis integration tests for atomic recovery snapshots.

Development-only.

Uses isolated Redis test keys and the existing Redis fixture.
Does not access PostgreSQL, production queues, or job handlers.

Run with RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os

import pytest

from apps.worker.jobs.redis_recovery_snapshot import (
    inspect_recovery_snapshot,
)
from tests.integration.test_redis_recovery_evidence import (
    redis_recovery_setup,
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration tests disabled",
    ),
]


async def inspect(client, raw, processing, pending, evidence):
    return await inspect_recovery_snapshot(
        client,
        raw,
        processing_key=processing,
        pending_key=pending,
        evidence_key=evidence,
    )


async def test_snapshot_single_processing(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-processing"}'

    await client.lpush(processing, raw)

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "processing"


async def test_snapshot_single_pending(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-pending"}'

    await client.lpush(pending, raw)

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "pending"


async def test_snapshot_missing(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-missing"}'

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "missing"


async def test_snapshot_duplicate_processing(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-duplicate-processing"}'

    await client.lpush(processing, raw, raw)

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "ambiguous"


async def test_snapshot_duplicate_pending(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-duplicate-pending"}'

    await client.lpush(pending, raw, raw)

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "ambiguous"


async def test_snapshot_processing_and_pending(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-conflicting-queues"}'

    await client.lpush(processing, raw)
    await client.lpush(pending, raw)

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "ambiguous"


async def test_snapshot_valid_evidence_with_pending(redis_recovery_setup):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-evidence-pending"}'

    await client.lpush(pending, raw)
    await client.set(evidence, "moved")

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "evidence_present"


async def test_snapshot_valid_evidence_without_queue_copy(
    redis_recovery_setup,
):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-evidence-no-copy"}'

    await client.set(evidence, "moved")

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "evidence_present"


async def test_snapshot_evidence_with_processing_is_uncertain(
    redis_recovery_setup,
):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-inconsistent-processing"}'

    await client.lpush(processing, raw)
    await client.set(evidence, "moved")

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "uncertain"


async def test_snapshot_unknown_evidence_is_uncertain(
    redis_recovery_setup,
):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-unknown-evidence"}'

    await client.set(evidence, "unexpected")

    assert await inspect(
        client, raw, processing, pending, evidence
    ) == "uncertain"


async def test_snapshot_inspection_does_not_modify_redis(
    redis_recovery_setup,
):
    client, processing, pending, evidence = redis_recovery_setup
    raw = '{"job_id":"snapshot-read-only"}'

    await client.lpush(processing, raw)
    await client.set(evidence, "moved")

    before_processing = await client.lrange(processing, 0, -1)
    before_pending = await client.lrange(pending, 0, -1)
    before_evidence = await client.get(evidence)

    result = await inspect(
        client, raw, processing, pending, evidence
    )

    assert result == "uncertain"

    assert await client.lrange(
        processing, 0, -1
    ) == before_processing

    assert await client.lrange(
        pending, 0, -1
    ) == before_pending

    assert await client.get(evidence) == before_evidence
