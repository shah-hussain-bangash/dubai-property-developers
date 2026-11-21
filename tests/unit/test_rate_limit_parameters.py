"""Limiter configuration is validated before requests or Redis writes."""

import unittest
from unittest.mock import AsyncMock, Mock, patch

from apps.api.app.middleware.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    RedisFixedWindowRateLimiter,
)


class RateLimitParameterTests(unittest.TestCase):
    def test_invalid_request_quotas_are_rejected_by_both_limiters(self):
        client = Mock()
        for value in (0, -1, True, False, 1.5, "10", None):
            for backend in ("memory", "redis"):
                with (
                    self.subTest(value=value, backend=backend),
                    self.assertRaisesRegex(ValueError, "limit must be"),
                ):
                    if backend == "memory":
                        InMemoryFixedWindowRateLimiter(value)
                    else:
                        RedisFixedWindowRateLimiter(client, value)
        self.assertEqual(client.mock_calls, [])

    def test_invalid_windows_are_rejected_before_any_redis_command(self):
        client = Mock()
        for value in (0, -1, True, False, 1.5, "60", None, 2**31, 10**100):
            for backend in ("memory", "redis"):
                with (
                    self.subTest(value=value, backend=backend),
                    self.assertRaisesRegex(ValueError, "window_seconds must be"),
                ):
                    if backend == "memory":
                        InMemoryFixedWindowRateLimiter(1, window_seconds=value)
                    else:
                        RedisFixedWindowRateLimiter(client, 1, window_seconds=value)
        self.assertEqual(client.mock_calls, [])

    def test_valid_integer_boundaries_are_preserved(self):
        client = Mock()
        for limit, window in ((1, 1), (120, 60), (1, 2**31 - 1)):
            with self.subTest(limit=limit, window=window):
                limiters = (
                    InMemoryFixedWindowRateLimiter(limit, window),
                    RedisFixedWindowRateLimiter(client, limit, window),
                )
                for limiter in limiters:
                    self.assertEqual(limiter.limit, limit)
                    self.assertEqual(limiter.window, window)


class SmallWindowRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_minimum_window_enforces_and_resets_quota(self):
        limiter = InMemoryFixedWindowRateLimiter(1, window_seconds=1)
        with patch("apps.api.app.middleware.rate_limit.time.time", return_value=1700000000.0):
            self.assertTrue(await limiter.hit("fixture-client"))
            self.assertFalse(await limiter.hit("fixture-client"))
        with patch("apps.api.app.middleware.rate_limit.time.time", return_value=1700000001.0):
            self.assertTrue(await limiter.hit("fixture-client"))

    async def test_redis_minimum_window_reaches_atomic_operation_unchanged(self):
        client = AsyncMock()
        client.eval.return_value = 1
        limiter = RedisFixedWindowRateLimiter(client, 1, window_seconds=1)
        self.assertTrue(await limiter.hit("fixture-client"))
        self.assertEqual(client.eval.await_args.args[-1], 1)
