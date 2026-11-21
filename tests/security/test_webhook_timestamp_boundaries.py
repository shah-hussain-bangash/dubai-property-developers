"""Reject extreme webhook timestamps without consuming authenticated replay state."""

import secrets
import unittest

from core.exceptions.errors import WebhookVerificationError
from core.security.webhooks import InMemoryNonceStore, compute_hmac_sha256, verify_hmac_sha256


class WebhookTimestampBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_out_of_window_timestamps_preserve_nonce(self):
        secret = secrets.token_hex(32)
        body, current = b'{"fixture":"timestamp-validation"}', 1700000000.0
        for timestamp in ("9" * 400, "-" + "9" * 400, "1699999699", "1700000301"):
            with self.subTest(timestamp=timestamp):
                request = {
                    "secret": secret,
                    "body": body,
                    "timestamp": timestamp,
                    "signature": compute_hmac_sha256(secret, timestamp, body),
                    "nonce": "fixture-request-nonce",
                    "nonce_store": InMemoryNonceStore(),
                    "now": current,
                }
                with self.assertRaisesRegex(
                    WebhookVerificationError, "timestamp outside tolerance window"
                ) as rejected:
                    await verify_hmac_sha256(**request)
                self.assertEqual(rejected.exception.status_code, 401)
                request["timestamp"] = "1700000000"
                request["signature"] = compute_hmac_sha256(secret, request["timestamp"], body)
                await verify_hmac_sha256(**request)
                with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                    await verify_hmac_sha256(**request)

    async def test_exact_tolerance_boundaries_accept_once(self):
        secret = secrets.token_hex(32)
        body, current = b'{"fixture":"timestamp-boundary"}', 1700000000.0
        for timestamp in ("1699999700", "1700000000", "1700000300"):
            with self.subTest(timestamp=timestamp):
                request = {
                    "secret": secret,
                    "body": body,
                    "timestamp": timestamp,
                    "signature": compute_hmac_sha256(secret, timestamp, body),
                    "nonce": "fixture-request-nonce",
                    "nonce_store": InMemoryNonceStore(),
                    "now": current,
                }
                await verify_hmac_sha256(**request)
                with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                    await verify_hmac_sha256(**request)
