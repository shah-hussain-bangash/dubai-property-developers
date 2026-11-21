"""Webhook signature verification and replay defence.

Two schemes are provided:
* ``verify_hmac_sha256`` - generic ``HMAC-SHA256(secret, f"{timestamp}.{body}")`` used for
  internal/n8n webhooks, combined with a timestamp tolerance and replay store.
* ``verify_meta_signature`` - Meta's ``X-Hub-Signature-256: sha256=<hex>`` header
  computed over the raw body with the app secret.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Protocol

from core.exceptions.errors import WebhookVerificationError


class NonceStore(Protocol):
    async def seen_before(self, nonce: str, ttl_seconds: int) -> bool:
        """Atomically record ``nonce``; return True if it was already present."""
        ...


class InMemoryNonceStore:
    def __init__(self) -> None:
        self._seen: dict[str, float] = {}

    async def seen_before(self, nonce: str, ttl_seconds: int) -> bool:
        now = time.time()
        self._seen = {k: exp for k, exp in self._seen.items() if exp > now}
        if nonce in self._seen:
            return True
        self._seen[nonce] = now + ttl_seconds
        return False


def compute_hmac_sha256(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


async def verify_hmac_sha256(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    nonce: str | None,
    nonce_store: NonceStore,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> None:
    if not signature or not timestamp or not nonce:
        raise WebhookVerificationError("missing signature, timestamp or nonce")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("invalid timestamp") from exc
    current = now if now is not None else time.time()
    # Compare bounds directly without converting an untrusted integer to float.
    if not current - tolerance_seconds <= ts <= current + tolerance_seconds:
        raise WebhookVerificationError("timestamp outside tolerance window")
    expected = compute_hmac_sha256(secret, timestamp, body)
    candidate = signature.removeprefix("sha256=")
    if not candidate.isascii() or not hmac.compare_digest(expected, candidate):
        raise WebhookVerificationError("signature mismatch")
    # The nonce is not signed. Deduplicate the authenticated message first so changing
    # the nonce cannot replay it, and a replay cannot consume a fresh nonce.
    # Timestamp bounds are inclusive; retain replay keys beyond the final valid instant.
    ttl_seconds = tolerance_seconds * 2 + 1
    if await nonce_store.seen_before(f"hmac-sha256:signature:{expected}", ttl_seconds):
        raise WebhookVerificationError("replayed request")
    if await nonce_store.seen_before(f"hmac-sha256:nonce:{nonce}", ttl_seconds):
        raise WebhookVerificationError("replayed request")


def verify_meta_signature(*, app_secret: str, body: bytes, header_value: str | None) -> None:
    if not header_value or not header_value.startswith("sha256="):
        raise WebhookVerificationError("missing or malformed X-Hub-Signature-256 header")
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    candidate = header_value.removeprefix("sha256=")
    if not candidate.isascii() or not hmac.compare_digest(expected, candidate):
        raise WebhookVerificationError("signature mismatch")
