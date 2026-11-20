
"""Atomic Redis recovery transition with durable-operation evidence.

Development-only; not connected to the deployed Docker worker.

The Lua script atomically moves one exact raw reservation and writes
an operation-specific marker. It refuses ambiguous reservations.

The marker has no automatic TTL. Production deployment requires an
explicit retention, persistence, and disaster-recovery policy.

Redis evidence is not proof of PostgreSQL ownership or exactly-once
execution. The coordinator must authenticate the envelope and hold
a valid PostgreSQL recovery lease.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal


RecoveryTransitionResult = Literal[
    "moved",
    "already_moved",
    "missing",
    "ambiguous",
]


# KEYS[1] = processing queue
# KEYS[2] = pending queue
# KEYS[3] = recovery operation evidence key
# ARGV[1] = exact authenticated raw message
#
# Return:
# 0 missing
# 1 moved
# 2 already_moved
# 3 ambiguous
RECOVERY_EVIDENCE_SCRIPT = """
if redis.call('EXISTS', KEYS[3]) == 1 then
    return 2
end

local processing_count = 0
local processing_messages = redis.call('LRANGE', KEYS[1], 0, -1)

for _, message in ipairs(processing_messages) do
    if message == ARGV[1] then
        processing_count = processing_count + 1
        if processing_count > 1 then
            return 3
        end
    end
end

local pending_count = 0
local pending_messages = redis.call('LRANGE', KEYS[2], 0, -1)

for _, message in ipairs(pending_messages) do
    if message == ARGV[1] then
        pending_count = pending_count + 1
        if pending_count > 0 then
            return 3
        end
    end
end

if processing_count == 0 then
    return 0
end

local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])

if removed ~= 1 then
    return redis.error_reply('Unexpected reservation removal')
end

redis.call('LPUSH', KEYS[2], ARGV[1])
redis.call('SET', KEYS[3], 'moved')

return 1
"""


def recovery_evidence_key(
    operation_id: uuid.UUID,
    *,
    prefix: str = "recovery:evidence",
) -> str:
    """Create a stable evidence key for a recovery operation."""

    if not isinstance(operation_id, uuid.UUID):
        raise ValueError("operation_id must be a UUID")

    if not isinstance(prefix, str) or not prefix.strip():
        raise ValueError("prefix is required")

    return f"{prefix}:{operation_id.hex}"


async def requeue_with_evidence(
    redis: Any,
    raw: str,
    *,
    processing_key: str,
    pending_key: str,
    evidence_key: str,
) -> RecoveryTransitionResult:
    """Move an unambiguous reservation and record Redis evidence.

    Results:
        moved: a reservation was moved, evidence was written
        already_moved: evidence key already existed
        missing: no reservation found and no evidence exists
        ambiguous: duplicate reservation or pending copy detected

    Missing and ambiguous outcomes must not authorize republishing.
    """

    if not isinstance(raw, str) or not raw:
        raise ValueError("raw message is required")

    keys = [processing_key, pending_key, evidence_key]

    if any(
        not isinstance(key, str) or not key.strip()
        for key in keys
    ):
        raise ValueError("All Redis keys are required")

    if len(set(keys)) != 3:
        raise ValueError("Redis keys must be distinct")

    result = await redis.eval(
        RECOVERY_EVIDENCE_SCRIPT,
        3,
        processing_key,
        pending_key,
        evidence_key,
        raw,
    )

    outcomes = {
        0: "missing",
        1: "moved",
        2: "already_moved",
        3: "ambiguous",
    }

    try:
        return outcomes[int(result)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Unexpected Redis recovery transition result"
        ) from exc
