
"""Integration test for a lost Redis recovery response.

Development-only. Uses real PostgreSQL and isolated Redis keys.

The first Redis transition succeeds, but its response is
simulated as lost. Replaying the same recovery operation must
not duplicate the Redis reservation.

Run with RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import apps.worker.jobs.guarded_recovery_transition as guarded_module

from apps.worker.jobs.guarded_recovery_transition import (
    GuardedRecoveryError,
)

from apps.worker.jobs.redis_recovery_evidence import (
    requeue_with_evidence,
)

# Reuse the existing integration fixture and helpers.
# The original eight-test file remains unchanged.
from tests.integration.test_guarded_recovery_real_redis import (
    create_case,
    environment,
    invoke,
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration tests disabled",
    ),
]


# ---------------------------------------------------------
# TEST 9: LOST REDIS RESPONSE AND EVIDENCE REPLAY
# ---------------------------------------------------------


async def test_lost_redis_response_replay_is_idempotent(
    environment,
):
    """A lost response must not cause duplicate requeue.

    The Redis Lua script executes successfully, but the
    caller receives a simulated timeout afterward.

    A second attempt should detect existing evidence
    and return already_moved without changing the queue.
    """

    case = await create_case(environment)
    client = environment["redis"]

    # Create one fictional reservation.
    await client.lpush(
        case["processing_key"],
        case["raw"],
    )

    response_lost = False

    original_requeue = requeue_with_evidence

    async def lose_first_response(*args, **kwargs):
        nonlocal response_lost

        # Execute the actual Redis Lua transition.
        result = await original_requeue(
            *args,
            **kwargs,
        )

        # Simulate losing the successful response.
        if not response_lost:
            assert result == "moved"

            response_lost = True

            raise TimeoutError(
                "Simulated lost Redis response after execution"
            )

        return result

    with patch.object(
        guarded_module,
        "requeue_with_evidence",
        lose_first_response,
    ):
        # Attempt 1: Redis succeeds, but the coordinator
        # observes a timeout.
        with pytest.raises(
            GuardedRecoveryError,
            match="Redis recovery transition timed out",
        ):
            await invoke(
                environment,
                case,
            )

        assert response_lost is True

        # Redis completed the transition despite the error.
        assert await client.lrange(
            case["processing_key"],
            0,
            -1,
        ) == []

        assert await client.lrange(
            case["pending_key"],
            0,
            -1,
        ) == [case["raw"]]

        assert await client.get(
            case["evidence_key"]
        ) == "moved"

        # Attempt 2: Replay the same recovery operation.
        result = await invoke(
            environment,
            case,
        )

        assert result == "already_moved"

        # Confirm that no duplicate reservation was created.
        assert await client.llen(
            case["pending_key"]
        ) == 1

        assert await client.llen(
            case["processing_key"]
        ) == 0

        assert await client.get(
            case["evidence_key"]
        ) == "moved"
