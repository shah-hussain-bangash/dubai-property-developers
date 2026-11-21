"""Malformed signatures must fail authentication without touching replay state."""

import hashlib
import hmac
import secrets
import unittest

from core.exceptions.errors import WebhookVerificationError
from core.security.webhooks import (
    InMemoryNonceStore,
    compute_hmac_sha256,
    verify_hmac_sha256,
    verify_meta_signature,
)


class MalformedWebhookSignatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_generic_malformed_signatures_preserve_nonce(self):
        secret = secrets.token_hex(32)
        timestamp, body = "1700000000", b'{"fixture":"signature-validation"}'
        digest = compute_hmac_sha256(secret, timestamp, body)
        for signature in (
            "é" * 64,
            "sha256=" + "é" * 64,
            digest[:-1] + "é",
            "sha256=" + digest[:-1] + "é",
            "\u200b" + digest,
            digest + "\x00",
            "g" * 64,
            digest[:-1],
            digest + "0",
            "SHA256=" + digest,
        ):
            with self.subTest(signature=signature):
                store = InMemoryNonceStore()
                request = {
                    "secret": secret,
                    "body": body,
                    "timestamp": timestamp,
                    "nonce": "fixture-request-nonce",
                    "nonce_store": store,
                    "now": 1700000000,
                }
                with self.assertRaises(WebhookVerificationError) as rejected:
                    await verify_hmac_sha256(signature=signature, **request)
                self.assertEqual(str(rejected.exception), "signature mismatch")
                self.assertEqual(rejected.exception.status_code, 401)
                self.assertEqual(store._seen, {})
                await verify_hmac_sha256(signature=digest, **request)
                with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                    await verify_hmac_sha256(signature=digest, **request)

    async def test_generic_valid_signature_forms_are_accepted(self):
        secret = secrets.token_hex(32)
        timestamp, body = "1700000000", b'{"fixture":"valid-signature"}'
        digest = compute_hmac_sha256(secret, timestamp, body)
        for signature in (digest, "sha256=" + digest):
            with self.subTest(signature=signature):
                await verify_hmac_sha256(
                    secret=secret,
                    body=body,
                    signature=signature,
                    timestamp=timestamp,
                    nonce="fixture-request-nonce",
                    nonce_store=InMemoryNonceStore(),
                    now=1700000000,
                )

    def test_meta_malformed_signatures_raise_authentication_error(self):
        secret, body = secrets.token_hex(32), b'{"entry":[]}'
        # Meta signs only the raw body; the generic scheme includes a timestamp.
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        for suffix in (
            "é" * 64,
            digest[:-1] + "é",
            "\u200b" + digest,
            digest + "\x00",
            "g" * 64,
            digest[:-1],
            digest + "0",
        ):
            with self.subTest(suffix=suffix):
                with self.assertRaises(WebhookVerificationError) as rejected:
                    verify_meta_signature(
                        app_secret=secret, body=body, header_value="sha256=" + suffix
                    )
                self.assertEqual(str(rejected.exception), "signature mismatch")
                self.assertEqual(rejected.exception.status_code, 401)

    def test_meta_valid_signature_is_accepted(self):
        secret, body = secrets.token_hex(32), b'{"entry":[]}'
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        verify_meta_signature(app_secret=secret, body=body, header_value="sha256=" + digest)
