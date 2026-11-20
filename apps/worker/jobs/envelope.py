"""Job envelope and reliable Redis queue helpers.

Pending:     queue:jobs
Processing:  queue:jobs:processing
Dead letter: queue:jobs:dead

Jobs are reserved using BLMOVE. Acknowledgement and
retry/dead-letter transitions use atomic Redis scripts.

Automatic recovery of abandoned processing jobs and
lease management are separate future improvements.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

QUEUE_KEY = "queue:jobs"
PROCESSING_KEY = "queue:jobs:processing"
DEAD_LETTER_KEY = "queue:jobs:dead"


# Remove a reserved job only if it exists.
ACK_SCRIPT = """
local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])
return removed
"""


# Atomically remove the original reservation and enqueue
# its updated retry/dead-letter representation.
#
# Do not create a new queue entry when the reservation
# is missing. This avoids duplicate transitions.
TRANSITION_SCRIPT = """
local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])

if removed ~= 1 then
    return 0
end

redis.call('LPUSH', KEYS[2], ARGV[2])
return 1
"""


class JobEnvelope(BaseModel):
    """Validated background-job message."""

    job_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    job_type: str
    tenant_id: str

    payload: dict[str, Any] = Field(default_factory=dict)

    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)

    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None


async def enqueue(redis: Any, job: JobEnvelope) -> str:
    """Append a new job to the pending queue."""

    await redis.lpush(
        QUEUE_KEY,
        job.model_dump_json(),
    )
    return job.job_id


async def reserve_job(
    redis: Any,
    timeout: int = 5,  # noqa: ASYNC109 -- This is a Redis blocking timeout or a parametrized timeout fixture, not a task deadline.
) -> str | None:
    """Atomically move the oldest pending job into processing."""

    return await redis.blmove(
        QUEUE_KEY,
        PROCESSING_KEY,
        timeout,
        "RIGHT",
        "LEFT",
    )


async def acknowledge_job(
    redis: Any,
    raw: str,
) -> bool:
    """Acknowledge one reserved job atomically."""

    removed = await redis.eval(
        ACK_SCRIPT,
        1,
        PROCESSING_KEY,
        raw,
    )
    return int(removed) == 1


async def transition_job(
    redis: Any,
    original_raw: str,
    updated_job: JobEnvelope | str,
    *,
    dead_letter: bool = False,
) -> bool:
    """Atomically move a reserved job to retry or dead-letter.

    The original reservation must still exist.
    """

    destination = DEAD_LETTER_KEY if dead_letter else QUEUE_KEY

    updated_raw = updated_job if isinstance(updated_job, str) else updated_job.model_dump_json()

    moved = await redis.eval(
        TRANSITION_SCRIPT,
        2,
        PROCESSING_KEY,
        destination,
        original_raw,
        updated_raw,
    )

    return int(moved) == 1


async def get_queue_counts(
    redis: Any,
) -> dict[str, int]:
    """Read the current queue sizes."""

    pipeline = redis.pipeline(transaction=False)

    pipeline.llen(QUEUE_KEY)
    pipeline.llen(PROCESSING_KEY)
    pipeline.llen(DEAD_LETTER_KEY)

    pending, processing, dead = await pipeline.execute()

    return {
        "pending": int(pending),
        "processing": int(processing),
        "dead": int(dead),
    }
