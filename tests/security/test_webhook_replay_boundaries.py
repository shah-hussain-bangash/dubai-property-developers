"""Malformed webhook requests must not prevent a later authenticated request."""

import secrets

import pytest

from core.exceptions.errors import WebhookVerificationError
from core.security.webhooks import InMemoryNonceStore, compute_hmac_sha256, verify_hmac_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("signature", None, "missing signature"),
        ("timestamp", None, "missing signature"),
        ("nonce", None, "missing signature"),
        ("timestamp", "not-a-timestamp", "invalid timestamp"),
    ],
)
async def test_invalid_headers_do_not_consume_authenticated_request_nonce(field, value, reason):
    secret = secrets.token_hex(32)
    timestamp = "1700000000"
    body = b'{"fixture":"webhook-replay-check"}'
    valid = {
        "secret": secret,
        "body": body,
        "signature": compute_hmac_sha256(secret, timestamp, body),
        "timestamp": timestamp,
        "nonce": "fixture-request-nonce",
        "nonce_store": InMemoryNonceStore(),
        "now": 1700000000,
    }
    with pytest.raises(WebhookVerificationError, match=reason):
        await verify_hmac_sha256(**{**valid, field: value})
    await verify_hmac_sha256(**valid)
    with pytest.raises(WebhookVerificationError, match="replayed request"):
        await verify_hmac_sha256(**valid)
