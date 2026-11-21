"""Replay retention must cover the inclusive timestamp acceptance window."""

import secrets
import unittest
from unittest.mock import patch

from core.exceptions.errors import WebhookVerificationError
from core.security.webhooks import InMemoryNonceStore, compute_hmac_sha256, verify_hmac_sha256


class WebhookReplayExpiryTests(unittest.IsolatedAsyncioTestCase):
    def request(self, *, secret, store, timestamp, nonce="fixture-nonce", tolerance=300):
        body = b'{"fixture":"replay-expiry"}'
        return {
            "secret": secret,
            "body": body,
            "timestamp": timestamp,
            "signature": compute_hmac_sha256(secret, timestamp, body),
            "nonce": nonce,
            "nonce_store": store,
            "tolerance_seconds": tolerance,
        }

    async def test_future_boundary_request_cannot_replay_at_last_valid_instant(self):
        for nonce in ("fixture-nonce", "replacement-nonce"):
            with self.subTest(nonce=nonce):
                request = self.request(
                    secret=secrets.token_hex(32),
                    store=InMemoryNonceStore(),
                    timestamp="1700000300",
                )
                with patch("core.security.webhooks.time.time", return_value=1700000000.0) as clock:
                    await verify_hmac_sha256(**request)
                    for elapsed in (599.5, 600.0):
                        clock.return_value = 1700000000.0 + elapsed
                        with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                            await verify_hmac_sha256(**{**request, "nonce": nonce})
                    clock.return_value = 1700000600.001
                    with self.assertRaisesRegex(WebhookVerificationError, "outside tolerance"):
                        await verify_hmac_sha256(**request)

    async def test_zero_tolerance_still_rejects_replay(self):
        request = self.request(
            secret=secrets.token_hex(32),
            store=InMemoryNonceStore(),
            timestamp="1700000000",
            tolerance=0,
        )
        with patch("core.security.webhooks.time.time", return_value=1700000000.0) as clock:
            await verify_hmac_sha256(**request)
            for nonce in ("fixture-nonce", "replacement-nonce"):
                with self.subTest(nonce=nonce):
                    with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                        await verify_hmac_sha256(**{**request, "nonce": nonce})
            clock.return_value = 1700000000.001
            with self.assertRaisesRegex(WebhookVerificationError, "outside tolerance"):
                await verify_hmac_sha256(**request)

    async def test_expired_nonce_can_be_used_by_a_fresh_signed_request(self):
        secret, store = secrets.token_hex(32), InMemoryNonceStore()
        with patch("core.security.webhooks.time.time", return_value=1700000000.0) as clock:
            await verify_hmac_sha256(
                **self.request(secret=secret, store=store, timestamp="1700000000")
            )
            clock.return_value = 1700000601.0
            await verify_hmac_sha256(
                **self.request(secret=secret, store=store, timestamp="1700000601")
            )
