"""Experimental Redis generation-fenced recovery transition.

Development-only. Not connected to the production worker.

The fencing key must be populated by a trusted coordinator.
This module does not synchronize PostgreSQL ownership with Redis.
"""

from __future__ import annotations

from typing import Any, Literal

FencedRecoveryResult = Literal[
    "moved",
    "already_moved",
    "missing",
    "ambiguous",
    "stale",
    "uninitialized",
]


FENCED_RECOVERY_SCRIPT = """
-- KEYS[1]: processing
-- KEYS[2]: pending
-- KEYS[3]: evidence
-- KEYS[4]: fencing generation
-- ARGV[1]: exact raw reservation
-- ARGV[2]: caller's generation

local current = redis.call('GET', KEYS[4])

if not current then
    return 5
end

local expected = tonumber(current)
local provided = tonumber(ARGV[2])

if not expected or not provided or provided ~= expected then
    return 4
end

if redis.call('EXISTS', KEYS[3]) == 1 then
    return 2
end

local processing_count = 0

for _, message in ipairs(
    redis.call('LRANGE', KEYS[1], 0, -1)
) do
    if message == ARGV[1] then
        processing_count = processing_count + 1
        if processing_count > 1 then
            return 3
        end
    end
end

for _, message in ipairs(
    redis.call('LRANGE', KEYS[2], 0, -1)
) do
    if message == ARGV[1] then
        return 3
    end
end

if processing_count == 0 then
    return 0
end

local removed = redis.call(
    'LREM', KEYS[1], 1, ARGV[1]
)

if removed ~= 1 then
    return redis.error_reply(
        'Unexpected reservation removal'
    )
end

redis.call('LPUSH', KEYS[2], ARGV[1])
redis.call('SET', KEYS[3], 'moved')

return 1
"""


async def requeue_with_fencing(
    redis: Any,
    raw: str,
    *,
    processing_key: str,
    pending_key: str,
    evidence_key: str,
    fencing_key: str,
    generation: int,
) -> FencedRecoveryResult:
    """Execute an experimental generation-checked transition."""

    if not isinstance(raw, str) or not raw:
        raise ValueError("raw reservation is required")

    keys = [
        processing_key,
        pending_key,
        evidence_key,
        fencing_key,
    ]

    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise ValueError("All Redis keys are required")

    if len(set(keys)) != 4:
        raise ValueError("Redis keys must be distinct")

    if type(generation) is not int or generation < 1:
        raise ValueError("generation must be a positive integer")

    result = await redis.eval(
        FENCED_RECOVERY_SCRIPT,
        4,
        processing_key,
        pending_key,
        evidence_key,
        fencing_key,
        raw,
        generation,
    )

    outcomes: dict[int, FencedRecoveryResult] = {
        0: "missing",
        1: "moved",
        2: "already_moved",
        3: "ambiguous",
        4: "stale",
        5: "uninitialized",
    }

    try:
        return outcomes[int(result)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Unexpected fenced recovery result") from exc
