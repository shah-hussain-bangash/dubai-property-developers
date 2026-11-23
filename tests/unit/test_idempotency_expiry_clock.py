"""Replay-cache TTLs measure elapsed time rather than calendar-clock changes."""

import unittest
from unittest.mock import patch

from core.resilience.idempotency import InMemoryIdempotencyStore


class IdempotencyExpiryClockTests(unittest.IsolatedAsyncioTestCase):
    async def test_forward_wall_clock_jump_does_not_expire_a_live_result(self):
        store = InMemoryIdempotencyStore()
        with (
            patch("core.resilience.idempotency.time.monotonic") as elapsed,
            patch("core.resilience.idempotency.time.time") as wall,
        ):
            elapsed.return_value = 100.0
            wall.return_value = 1000.0
            await store.put("fixture-key", {"fixture": "result"}, 30)
            elapsed.return_value = 110.0
            wall.return_value = 1000000.0

            self.assertEqual(await store.get("fixture-key"), {"fixture": "result"})

    async def test_backward_wall_clock_jump_does_not_extend_an_expired_result(self):
        store = InMemoryIdempotencyStore()
        with (
            patch("core.resilience.idempotency.time.monotonic") as elapsed,
            patch("core.resilience.idempotency.time.time") as wall,
        ):
            elapsed.return_value = 100.0
            wall.return_value = 1000.0
            await store.put("fixture-key", {"fixture": "result"}, 30)
            elapsed.return_value = 131.0
            wall.return_value = 1.0

            self.assertIsNone(await store.get("fixture-key"))

    async def test_result_expires_at_deadline_and_stays_removed(self):
        store = InMemoryIdempotencyStore()
        with patch("core.resilience.idempotency.time.monotonic") as elapsed:
            elapsed.return_value = 100.0
            await store.put("fixture-key", {"fixture": "result"}, 30)
            elapsed.return_value = 129.999
            self.assertEqual(await store.get("fixture-key"), {"fixture": "result"})
            elapsed.return_value = 130.0
            self.assertIsNone(await store.get("fixture-key"))
            elapsed.return_value = 100.0
            self.assertIsNone(await store.get("fixture-key"))

    async def test_zero_ttl_is_expired_immediately(self):
        store = InMemoryIdempotencyStore()
        with patch("core.resilience.idempotency.time.monotonic", return_value=100.0):
            await store.put("fixture-key", {"fixture": "result"}, 0)
            self.assertIsNone(await store.get("fixture-key"))
