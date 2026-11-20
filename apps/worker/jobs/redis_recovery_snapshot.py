"""Atomic, read-only Redis recovery snapshot.

Development-only. Not connected to the running Docker worker.

Reads processing queue, pending queue, and operation evidence
within one Redis Lua execution.

A Redis snapshot cannot prove PostgreSQL lease ownership,
message authenticity, Redis durability, or exactly-once execution.
Do not use this result alone to authorize recovery completion.
"""

from __future__ import annotations

from typing import Any, Literal

RecoverySnapshotResult = Literal[
    "processing",
    "pending",
    "missing",
    "ambiguous",
    "evidence_present",
    "uncertain",
]


RECOVERY_SNAPSHOT_SCRIPT = """
-- KEYS[1] = processing queue
-- KEYS[2] = pending queue
-- KEYS[3] = recovery evidence
-- ARGV[1] = exact raw reservation

local processing_count = 0
local pending_count = 0

for _, message in ipairs(
    redis.call('LRANGE', KEYS[1], 0, -1)
) do
    if message == ARGV[1] then
        processing_count = processing_count + 1
    end
end

for _, message in ipairs(
    redis.call('LRANGE', KEYS[2], 0, -1)
) do
    if message == ARGV[1] then
        pending_count = pending_count + 1
    end
end

local evidence = redis.call('GET', KEYS[3])

-- Unexpected evidence values are uncertain.
if evidence and evidence ~= 'moved' then
    return 5
end

-- Duplicate or conflicting queue occurrences.
if processing_count > 1
    or pending_count > 1
    or (processing_count > 0 and pending_count > 0)
then
    return 3
end

if evidence == 'moved' then
    if processing_count > 0 then
        return 5
    end

    return 4
end

if processing_count == 1 then
    return 0
end

if pending_count == 1 then
    return 1
end

return 2
"""


async def inspect_recovery_snapshot(
    redis: Any,
    raw: str,
    *,
    processing_key: str,
    pending_key: str,
    evidence_key: str,
) -> RecoverySnapshotResult:
    """Read a consistent Redis-only recovery snapshot.

    Returns:
        processing: one processing copy and no evidence
        pending: one pending copy and no evidence
        missing: no copies and no evidence
        ambiguous: duplicate or conflicting queue copies
        evidence_present: moved evidence with no processing copy
        uncertain: inconsistent or unsupported evidence state

    All outcomes are observations, never ownership authorization.
    """

    if not isinstance(raw, str) or not raw:
        raise ValueError("raw message is required")

    keys = [processing_key, pending_key, evidence_key]

    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise ValueError("All Redis keys are required")

    if len(set(keys)) != 3:
        raise ValueError("Redis keys must be distinct")

    result = await redis.eval(
        RECOVERY_SNAPSHOT_SCRIPT,
        3,
        processing_key,
        pending_key,
        evidence_key,
        raw,
    )

    outcomes = {
        0: "processing",
        1: "pending",
        2: "missing",
        3: "ambiguous",
        4: "evidence_present",
        5: "uncertain",
    }

    try:
        return outcomes[int(result)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Unexpected Redis recovery snapshot result") from exc
