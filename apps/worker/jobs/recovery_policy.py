
"""Read-only policy for PostgreSQL-backed Redis reservation recovery.

This module only classifies a job's state. It does not:
- Claim or modify PostgreSQL jobs.
- Move, acknowledge, or delete Redis messages.
- Execute handlers.
- Authenticate job payloads.

Before performing any recovery action, the coordinator must
authenticate the Redis envelope, verify the tenant/job identity,
and acquire the necessary database-level recovery ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from apps.worker.jobs.envelope import JobEnvelope


RecoveryAction = Literal[
    "active_lease",
    "expired_lease",
    "retry_not_due",
    "retry_due",
    "terminal_candidate",
    "pending_candidate",
    "manual_review",
]


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str


def classify_reservation(
    job: JobEnvelope,
    record: Any | None,
    *,
    now: datetime | None = None,
) -> RecoveryDecision:
    """Classify a Redis reservation using PostgreSQL metadata.

    All decisions are advisory. In particular, candidate and
    expired states do not authorize a Redis mutation by themselves.
    """

    if now is None:
        now = datetime.now(UTC)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if record is None:
        return RecoveryDecision(
            "manual_review",
            "No matching PostgreSQL registration",
        )

    if (
        getattr(record, "job_id", None) != job.job_id
        or getattr(record, "job_type", None) != job.job_type
        or getattr(record, "max_attempts", None) != job.max_attempts
    ):
        return RecoveryDecision(
            "manual_review",
            "Job registration metadata does not match",
        )

    status = getattr(record, "status", None)

    if status in {"succeeded", "failed"}:
        return RecoveryDecision(
            "terminal_candidate",
            "Job is already terminal in PostgreSQL",
        )

    if status == "processing":
        expiry = getattr(record, "lease_expires_at", None)

        if (
            expiry is None
            or expiry.tzinfo is None
            or expiry.utcoffset() is None
        ):
            return RecoveryDecision(
                "manual_review",
                "Processing lease has no valid expiry",
            )

        if expiry > now:
            return RecoveryDecision(
                "active_lease",
                "PostgreSQL processing lease is still active",
            )

        return RecoveryDecision(
            "expired_lease",
            "Processing lease expired; DB recovery required",
        )

    if status == "retrying":
        retry_at = getattr(record, "next_retry_at", None)

        if (
            retry_at is None
            or retry_at.tzinfo is None
            or retry_at.utcoffset() is None
        ):
            return RecoveryDecision(
                "manual_review",
                "Retry schedule is missing or invalid",
            )

        if retry_at > now:
            return RecoveryDecision(
                "retry_not_due",
                "PostgreSQL retry time has not arrived",
            )

        return RecoveryDecision(
            "retry_due",
            "Retry is due; coordinated requeue required",
        )

    if status == "pending":
        return RecoveryDecision(
            "pending_candidate",
            "Job is registered but has no processing claim",
        )

    return RecoveryDecision(
        "manual_review",
        "Unknown or inconsistent PostgreSQL job state",
    )
