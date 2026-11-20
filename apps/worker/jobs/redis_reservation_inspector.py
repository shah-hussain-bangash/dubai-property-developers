
"""Read-only Redis reservation inspection for job recovery.

Development-only. This module does not change Redis queue state.

A queue-location observation is not a lock or proof that a
particular recovery operation performed the transition.

Callers must authenticate the original job envelope separately.
"""

from __future__ import annotations

from typing import Any, Literal


ReservationLocation = Literal[
    "processing",
    "pending",
    "missing",
    "ambiguous",
]


async def inspect_reservation(
    redis: Any,
    raw: str,
    *,
    processing_key: str,
    pending_key: str,
) -> ReservationLocation:
    """Inspect exact-message occurrences in two Redis lists.

    Returns:
        processing: exactly one processing occurrence, zero pending
        pending: zero processing occurrences, exactly one pending
        missing: no occurrences in either list
        ambiguous: any other combination

    This is a read-only snapshot. Lists may change immediately
    after the inspection, so callers must not use the result
    alone to authorize a Redis transition or PostgreSQL commit.
    """

    if not isinstance(raw, str) or not raw:
        raise ValueError("raw message is required")

    if not processing_key or not pending_key:
        raise ValueError("Both Redis queue keys are required")

    if processing_key == pending_key:
        raise ValueError("Source and destination must differ")

    # LPOS COUNT 0 returns every matching position.
    # This avoids downloading the full queue into Python.
    processing_positions = await redis.lpos(
        processing_key,
        raw,
        count=0,
    )

    pending_positions = await redis.lpos(
        pending_key,
        raw,
        count=0,
    )

    processing_count = len(processing_positions or [])
    pending_count = len(pending_positions or [])

    if processing_count == 1 and pending_count == 0:
        return "processing"

    if processing_count == 0 and pending_count == 1:
        return "pending"

    if processing_count == 0 and pending_count == 0:
        return "missing"

    return "ambiguous"
