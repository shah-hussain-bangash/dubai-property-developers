"""Redis limiter outcomes and failures use a single atomic server operation."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from apps.api.app.middleware.rate_limit import RedisFixedWindowRateLimiter


class RedisRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_threshold_decisions_use_atomic_counter_result(self):
        client = AsyncMock()
        client.eval.side_effect = [1, 3, 4]
        limiter = RedisFixedWindowRateLimiter(client, limit=3)
        with patch("apps.api.app.middleware.rate_limit.time.time", return_value=1700000000.0):
            self.assertTrue(await limiter.hit("fixture-client"))
            self.assertTrue(await limiter.hit("fixture-client"))
            self.assertFalse(await limiter.hit("fixture-client"))
        self.assertEqual(client.eval.await_count, 3)
        client.incr.assert_not_awaited()
        client.expire.assert_not_awaited()

    async def test_redis_failure_propagates_instead_of_allowing_request(self):
        client = AsyncMock()
        client.eval.side_effect = OSError("fixture-redis-unavailable")
        limiter = RedisFixedWindowRateLimiter(client, limit=3)
        with self.assertRaises(OSError):
            await limiter.hit("fixture-client")

    async def test_request_cancellation_propagates(self):
        client = AsyncMock()
        client.eval.side_effect = asyncio.CancelledError
        limiter = RedisFixedWindowRateLimiter(client, limit=3)
        with self.assertRaises(asyncio.CancelledError):
            await limiter.hit("fixture-client")
