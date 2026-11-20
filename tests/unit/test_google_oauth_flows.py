"""Redis command-contract tests with an in-memory fake; no server connection."""

import asyncio
import runpy
import secrets
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "core/security/google_oauth_flows.py"))
Store = module["GoogleOAuthFlowStore"]
FlowError = module["OAuthFlowError"]
ORG, OTHER = UUID(int=1), UUID(int=2)
STATE = "synthetic_google_state_1234567890"


class FakeRedis:
    def __init__(self):
        self.records = {}
        self.lock = asyncio.Lock()
        self.set = AsyncMock(side_effect=self._set)
        self.eval = AsyncMock(side_effect=self._eval)

    async def _set(self, key, value, *, nx, ex):
        async with self.lock:
            if key in self.records:
                return None
            self.records[key] = value
            return True

    async def _eval(self, script, count, key, expected):
        # Emulates the adapter's atomic compare/delete contract.
        async with self.lock:
            if self.records.get(key) == expected:
                del self.records[key]
                return 1
            return 0


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_reservation_uses_expiry_and_no_overwrite(self):
        redis = FakeRedis()
        binding = secrets.token_urlsafe(32)
        await Store(redis).reserve(STATE, ORG, binding)
        self.assertEqual(redis.set.await_args.kwargs, {"nx": True, "ex": 600})
        with self.assertRaises(FlowError):
            await Store(redis).reserve(STATE, ORG, binding)
        self.assertEqual(len(redis.records), 1)

    async def test_raw_state_and_binding_are_not_stored(self):
        redis = FakeRedis()
        binding = secrets.token_urlsafe(32)
        await Store(redis).reserve(STATE, ORG, binding)
        key, value = next(iter(redis.records.items()))
        self.assertNotIn(STATE, key)
        self.assertNotIn(binding, value)
        self.assertTrue(value.startswith(str(ORG) + "|"))

    async def test_flow_can_be_consumed_only_once(self):
        redis = FakeRedis()
        store = Store(redis)
        binding = secrets.token_urlsafe(32)
        await store.reserve(STATE, ORG, binding)
        self.assertTrue(await store.consume(STATE, ORG, binding))
        self.assertFalse(await store.consume(STATE, ORG, binding))
        script = redis.eval.await_args.args[0]
        self.assertIn("redis.call('GET'", script)
        self.assertIn("redis.call('DEL'", script)

    async def test_foreign_browser_or_organization_cannot_consume(self):
        redis = FakeRedis()
        store = Store(redis)
        binding = secrets.token_urlsafe(32)
        await store.reserve(STATE, ORG, binding)
        self.assertFalse(await store.consume(STATE, OTHER, binding))
        self.assertFalse(
            await store.consume(
                STATE,
                ORG,
                secrets.token_urlsafe(32),
            )
        )
        self.assertTrue(await store.consume(STATE, ORG, binding))

    async def test_concurrent_consumers_have_one_winner_in_fake(self):
        redis = FakeRedis()
        store = Store(redis)
        binding = secrets.token_urlsafe(32)
        await store.reserve(STATE, ORG, binding)
        results = await asyncio.gather(*[store.consume(STATE, ORG, binding) for _ in range(10)])
        self.assertEqual(sum(results), 1)

    async def test_missing_or_expired_record_denied(self):
        redis = FakeRedis()
        store = Store(redis)
        binding = secrets.token_urlsafe(32)
        self.assertFalse(await store.consume(STATE, ORG, binding))
        await store.reserve(STATE, ORG, binding)
        redis.records.clear()  # Simulate server expiry without waiting.
        self.assertFalse(await store.consume(STATE, ORG, binding))

    async def test_invalid_input_rejected_before_redis(self):
        redis = FakeRedis()
        store = Store(redis)
        for state, organization, binding in (
            ("short", ORG, secrets.token_urlsafe(32)),
            (STATE, "untrusted-organization", secrets.token_urlsafe(32)),
            (STATE, UUID(int=0), secrets.token_urlsafe(32)),
            (STATE, ORG, "invalid-binding"),
        ):
            with self.assertRaises(FlowError):
                await store.reserve(state, organization, binding)
        redis.set.assert_not_awaited()
        redis.eval.assert_not_awaited()

    async def test_storage_failures_are_sanitized(self):
        redis = FakeRedis()
        store = Store(redis)
        binding = secrets.token_urlsafe(32)
        redis.set.side_effect = RuntimeError("private connection diagnostic")
        with self.assertRaises(FlowError) as caught:
            await store.reserve(STATE, ORG, binding)
        self.assertNotIn("private", str(caught.exception))
        redis.eval.side_effect = RuntimeError("private connection diagnostic")
        with self.assertRaises(FlowError) as caught:
            await store.consume(STATE, ORG, binding)
        self.assertNotIn("private", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
