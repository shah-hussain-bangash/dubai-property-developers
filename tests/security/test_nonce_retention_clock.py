"""Wall-clock corrections cannot shorten or extend replay-record retention."""

import secrets
import unittest
from unittest.mock import patch

from core.exceptions.errors import WebhookVerificationError
from core.security.webhooks import InMemoryNonceStore, compute_hmac_sha256, verify_hmac_sha256


class NonceRetentionClockTests(unittest.IsolatedAsyncioTestCase):
    async def test_forward_wall_clock_jump_keeps_live_nonce(self):
        store = InMemoryNonceStore()
        with (
            patch("core.security.webhooks.time.monotonic", return_value=100.0) as timer,
            patch("core.security.webhooks.time.time", return_value=1000.0) as wall,
        ):
            self.assertFalse(await store.seen_before("fixture-nonce", 60))
            timer.return_value = 110.0
            wall.return_value = 1000000.0

            self.assertTrue(await store.seen_before("fixture-nonce", 60))

    async def test_backward_wall_clock_jump_does_not_extend_nonce_lifetime(self):
        store = InMemoryNonceStore()
        with (
            patch("core.security.webhooks.time.monotonic", return_value=100.0) as timer,
            patch("core.security.webhooks.time.time", return_value=1000.0) as wall,
        ):
            self.assertFalse(await store.seen_before("fixture-nonce", 60))
            timer.return_value = 161.0
            wall.return_value = 1.0

            self.assertFalse(await store.seen_before("fixture-nonce", 60))

    async def test_nonce_expires_at_deadline_without_refresh_on_replay(self):
        store = InMemoryNonceStore()
        with patch("core.security.webhooks.time.monotonic", return_value=100.0) as timer:
            self.assertFalse(await store.seen_before("fixture-nonce", 60))
            timer.return_value = 159.999
            self.assertTrue(await store.seen_before("fixture-nonce", 60))
            timer.return_value = 160.0

            self.assertFalse(await store.seen_before("fixture-nonce", 60))
            self.assertTrue(await store.seen_before("fixture-nonce", 60))

    async def test_clock_jump_and_correction_cannot_enable_signed_request_replay(self):
        store = InMemoryNonceStore()
        secret = secrets.token_hex(32)
        timestamp = "1700000000"
        body = b'{"fixture":"clock-correction"}'
        request = {
            "secret": secret,
            "body": body,
            "timestamp": timestamp,
            "signature": compute_hmac_sha256(secret, timestamp, body),
            "nonce": "fixture-original",
            "nonce_store": store,
        }
        with (
            patch("core.security.webhooks.time.monotonic", return_value=100.0) as timer,
            patch("core.security.webhooks.time.time", return_value=1700000000.0) as wall,
        ):
            await verify_hmac_sha256(**request)
            timer.return_value = 101.0
            wall.return_value = 1700001000.0
            await store.seen_before("fixture-unrelated-request", 601)
            timer.return_value = 102.0
            wall.return_value = 1700000002.0

            with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                await verify_hmac_sha256(**{**request, "nonce": "fixture-replacement"})
