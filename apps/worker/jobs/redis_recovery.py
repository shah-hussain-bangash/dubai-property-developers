"""Atomic Redis reservation transitions for job recovery.

This module provides queue operations only. PostgreSQL ownership,
payload authentication, and recovery authorization must be checked
by a separate coordinator.

Not connected to the running Docker worker.
"""

from __future__ import annotations

from typing import Any

RECOVER_SCRIPT = """
local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])

if removed ~= 1 then
    return 0
end

redis.call('LPUSH', KEYS[2], ARGV[1])
return 1
"""


ACK_STALE_SCRIPT = """
return redis.call('LREM', KEYS[1], 1, ARGV[1])
"""


async def requeue_reserved_job(
    redis: Any,
    raw: str,
    *,
    processing_key: str,
    pending_key: str,
) -> bool:
    """Atomically move exactly one matching reservation to pending."""

    if not raw:
        raise ValueError("raw message is required")

    if not processing_key or not pending_key:
        raise ValueError("Both Redis queue keys are required")

    if processing_key == pending_key:
        raise ValueError("Source and destination must differ")

    moved = await redis.eval(
        RECOVER_SCRIPT,
        2,
        processing_key,
        pending_key,
        raw,
    )

    return int(moved) == 1


async def acknowledge_stale_reservation(
    redis: Any,
    raw: str,
    *,
    processing_key: str,
) -> bool:
    """Remove exactly one matching terminal reservation."""

    if not raw:
        raise ValueError("raw message is required")

    if not processing_key:
        raise ValueError("Processing queue key is required")

    removed = await redis.eval(
        ACK_STALE_SCRIPT,
        1,
        processing_key,
        raw,
    )

    return int(removed) == 1
