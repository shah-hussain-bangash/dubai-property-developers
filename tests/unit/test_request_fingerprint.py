from __future__ import annotations

import math

import pytest

from core.resilience.request_fingerprint import (
    make_request_fingerprint,
)


def test_same_payload_different_key_order() -> None:
    first = make_request_fingerprint(
        "tenant-a",
        "whatsapp.send_message",
        {
            "recipient": "+971500000000",
            "message": "Hello",
        },
    )

    second = make_request_fingerprint(
        "tenant-a",
        "whatsapp.send_message",
        {
            "message": "Hello",
            "recipient": "+971500000000",
        },
    )

    assert first == second
    assert len(first) == 64


def test_different_payload_changes_fingerprint() -> None:
    first = make_request_fingerprint(
        "tenant-a", "crm.create_lead", {"budget": 1000000}
    )

    second = make_request_fingerprint(
        "tenant-a", "crm.create_lead", {"budget": 2000000}
    )

    assert first != second


def test_different_tool_changes_fingerprint() -> None:
    payload = {"id": "123"}

    first = make_request_fingerprint(
        "tenant-a", "crm.create_lead", payload
    )

    second = make_request_fingerprint(
        "tenant-a", "crm.update_lead", payload
    )

    assert first != second


def test_different_tenant_changes_fingerprint() -> None:
    payload = {"id": "123"}

    first = make_request_fingerprint(
        "tenant-a", "crm.create_lead", payload
    )

    second = make_request_fingerprint(
        "tenant-b", "crm.create_lead", payload
    )

    assert first != second


@pytest.mark.parametrize(
    "payload",
    [
        {"value": object()},
        {"value": math.nan},
        {"value": math.inf},
    ],
)
def test_invalid_payload_rejected(payload) -> None:
    with pytest.raises(ValueError):
        make_request_fingerprint(
            "tenant-a", "crm.create_lead", payload
        )


def test_invalid_identity_rejected() -> None:
    with pytest.raises(ValueError):
        make_request_fingerprint(
            "", "crm.create_lead", {}
        )

    with pytest.raises(ValueError):
        make_request_fingerprint(
            "tenant-a", "", {}
        )
