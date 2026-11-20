"""Read-only reporting for unresolved tool-execution claims.

This module does not access databases, execute tools, change claims,
or authorize reconciliation and retry operations.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any


def _aware_datetime(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")

    return value.astimezone(UTC)


def _priority(state: str, age_minutes: int) -> str:
    if state == "uncertain":
        return "critical"

    if age_minutes >= 30:
        return "high"

    if age_minutes >= 5:
        return "medium"

    return "low"


def build_reconciliation_report(
    records: Iterable[Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Produce safe, read-only investigation summaries.

    Only explicitly approved fields are returned. This function
    never changes input records or makes recovery decisions.
    """

    current_time = _aware_datetime(
        now if now is not None else datetime.now(UTC),
        "now",
    )

    report: list[dict[str, Any]] = []

    for record in records:
        state = record.state

        if state == "completed":
            continue

        if state not in ("in_progress", "uncertain"):
            raise ValueError(f"Unsupported reconciliation state: {state}")

        claimed_at = _aware_datetime(
            record.claimed_at,
            "claimed_at",
        )

        elapsed_seconds = (current_time - claimed_at).total_seconds()

        if elapsed_seconds < 0:
            raise ValueError("claimed_at cannot be in the future")

        age_minutes = int(elapsed_seconds // 60)

        report.append(
            {
                "tool_name": record.tool_name,
                "state": state,
                "age_minutes": age_minutes,
                "priority": _priority(state, age_minutes),
            }
        )

    return report
