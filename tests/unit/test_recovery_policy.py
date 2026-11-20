"""Read-only recovery policy tests.

No actual Redis, PostgreSQL, or external services are used.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from apps.worker.jobs.recovery_policy import classify_reservation

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def make_job():
    return JobEnvelope(
        job_id="fictional-recovery-job",
        tenant_id="demo-org",
        job_type="knowledge.ingest",
        payload={"document_id": "fictional-document"},
        max_attempts=3,
    )


def make_record(job, *, status="pending", **changes):
    data = {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "max_attempts": job.max_attempts,
        "status": status,
        "lease_expires_at": None,
        "next_retry_at": None,
    }

    data.update(changes)

    return SimpleNamespace(**data)


def test_active_lease_is_not_recovered():
    job = make_job()
    record = make_record(
        job,
        status="processing",
        lease_expires_at=NOW + timedelta(minutes=2),
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "active_lease"


def test_expired_lease_requires_recovery():
    job = make_job()
    record = make_record(
        job,
        status="processing",
        lease_expires_at=NOW - timedelta(seconds=1),
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "expired_lease"


def test_retry_not_due_remains_deferred():
    job = make_job()
    record = make_record(
        job,
        status="retrying",
        next_retry_at=NOW + timedelta(minutes=5),
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "retry_not_due"


def test_due_retry_is_identified():
    job = make_job()
    record = make_record(
        job,
        status="retrying",
        next_retry_at=NOW - timedelta(seconds=1),
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "retry_due"


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_terminal_job_is_cleanup_candidate(status):
    job = make_job()
    record = make_record(job, status=status)

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "terminal_candidate"


def test_pending_job_is_candidate_not_automatically_requeued():
    job = make_job()
    record = make_record(job, status="pending")

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "pending_candidate"


def test_missing_registration_requires_review():
    job = make_job()

    decision = classify_reservation(job, None, now=NOW)

    assert decision.action == "manual_review"


def test_identity_mismatch_requires_review():
    job = make_job()

    record = make_record(
        job,
        status="succeeded",
        job_id="different-job",
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "manual_review"


def test_missing_lease_expiry_requires_review():
    job = make_job()
    record = make_record(
        job,
        status="processing",
        lease_expires_at=None,
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "manual_review"


def test_missing_retry_timestamp_requires_review():
    job = make_job()
    record = make_record(
        job,
        status="retrying",
        next_retry_at=None,
    )

    decision = classify_reservation(job, record, now=NOW)

    assert decision.action == "manual_review"


def test_naive_current_time_is_rejected():
    job = make_job()
    record = make_record(job)

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        classify_reservation(
            job,
            record,
            now=datetime(2026, 10, 12, 12, 0),
        )
