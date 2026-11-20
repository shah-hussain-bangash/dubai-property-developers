from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.resilience.reconciliation_report import (
    build_reconciliation_report,
)


NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def make_record(state, minutes_old, tool="crm.create_lead"):
    return SimpleNamespace(
        id=uuid4(),
        idempotency_key="private-idempotency-key",
        tool_name=tool,
        state=state,
        claimed_at=NOW - timedelta(minutes=minutes_old),
        owner_token="private-owner-token",
        request_fingerprint="a" * 64,
        result_json={"secret": "private-result"},
    )


@pytest.mark.parametrize(
    "state,minutes_old,expected",
    [
        ("uncertain", 1, "critical"),
        ("uncertain", 100, "critical"),
        ("in_progress", 31, "high"),
        ("in_progress", 30, "high"),
        ("in_progress", 10, "medium"),
        ("in_progress", 5, "medium"),
        ("in_progress", 4, "low"),
    ],
)
def test_report_priority(
    state, minutes_old, expected
):
    records = [make_record(state, minutes_old)]

    report = build_reconciliation_report(
        records,
        now=NOW,
    )

    assert len(report) == 1
    assert report[0]["priority"] == expected
    assert report[0]["state"] == state
    assert report[0]["age_minutes"] == minutes_old


def test_report_does_not_expose_sensitive_fields():
    records = [make_record("uncertain", 15)]

    report = build_reconciliation_report(
        records,
        now=NOW,
    )

    serialized = repr(report)

    assert "private-idempotency-key" not in serialized
    assert "private-owner-token" not in serialized
    assert "private-result" not in serialized
    assert "aaaaaaaaaaaaaaaa" not in serialized


def test_completed_claims_are_not_reported():
    records = [
        make_record("completed", 100),
        make_record("uncertain", 20),
    ]

    report = build_reconciliation_report(
        records,
        now=NOW,
    )

    assert len(report) == 1
    assert report[0]["state"] == "uncertain"


def test_report_rejects_invalid_timestamp():
    record = make_record("in_progress", 5)
    record.claimed_at = datetime(2026, 10, 16, 11, 55)

    with pytest.raises(ValueError):
        build_reconciliation_report(
            [record],
            now=NOW,
        )


def test_report_does_not_mutate_claim():
    record = make_record("in_progress", 45)
    original_state = record.state
    original_owner = record.owner_token

    build_reconciliation_report(
        [record],
        now=NOW,
    )

    assert record.state == original_state
    assert record.owner_token == original_owner
