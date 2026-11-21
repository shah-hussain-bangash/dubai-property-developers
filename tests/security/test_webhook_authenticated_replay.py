"""A captured authenticated webhook cannot be replayed with a replacement nonce."""

import asyncio
import secrets
import unittest

from core.exceptions.errors import WebhookVerificationError
from core.security.webhooks import InMemoryNonceStore, compute_hmac_sha256, verify_hmac_sha256


class WebhookAuthenticatedReplayTests(unittest.IsolatedAsyncioTestCase):
    def request(self, *, secret, store, body=b'{"fixture":"original"}', nonce="original-nonce"):
        timestamp = "1700000000"
        return {
            "secret": secret,
            "body": body,
            "timestamp": timestamp,
            "signature": compute_hmac_sha256(secret, timestamp, body),
            "nonce": nonce,
            "nonce_store": store,
            "now": 1700000000.0,
        }

    async def test_replacement_nonce_cannot_replay_authenticated_message(self):
        for prefixed in (False, True):
            with self.subTest(prefixed=prefixed):
                secret, store = secrets.token_hex(32), InMemoryNonceStore()
                request = self.request(secret=secret, store=store)
                await verify_hmac_sha256(**request)
                replay = {**request, "nonce": "replacement-nonce"}
                if prefixed:
                    replay["signature"] = "sha256=" + replay["signature"]
                with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
                    await verify_hmac_sha256(**replay)
                # Rejecting a replay must not reserve the attacker's replacement nonce.
                fresh = self.request(
                    secret=secret,
                    store=store,
                    body=b'{"fixture":"fresh-message"}',
                    nonce="replacement-nonce",
                )
                await verify_hmac_sha256(**fresh)

    async def test_nonce_reuse_with_different_authenticated_body_is_rejected(self):
        secret, store = secrets.token_hex(32), InMemoryNonceStore()
        await verify_hmac_sha256(**self.request(secret=secret, store=store))
        with self.assertRaisesRegex(WebhookVerificationError, "replayed request"):
            await verify_hmac_sha256(
                **self.request(secret=secret, store=store, body=b'{"fixture":"different"}')
            )

    async def test_distinct_authenticated_messages_are_accepted(self):
        secret, store = secrets.token_hex(32), InMemoryNonceStore()
        await verify_hmac_sha256(**self.request(secret=secret, store=store))
        await verify_hmac_sha256(
            **self.request(
                secret=secret,
                store=store,
                body=b'{"fixture":"different"}',
                nonce="different-nonce",
            )
        )

    async def test_concurrent_replays_with_distinct_nonces_accept_only_once(self):
        secret, store = secrets.token_hex(32), InMemoryNonceStore()
        results = await asyncio.gather(
            *(
                verify_hmac_sha256(
                    **self.request(secret=secret, store=store, nonce=f"nonce-{index}")
                )
                for index in range(8)
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(result is None for result in results), 1)
        rejected = [result for result in results if result is not None]
        self.assertEqual(len(rejected), 7)
        self.assertTrue(all(isinstance(result, WebhookVerificationError) for result in rejected))
