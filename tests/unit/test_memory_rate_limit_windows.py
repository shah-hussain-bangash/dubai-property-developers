"""Fixed-window behavior is preserved when cleanup runs only on window changes."""

import asyncio
import unittest
from unittest.mock import patch

from apps.api.app.middleware.rate_limit import InMemoryFixedWindowRateLimiter


class MemoryRateLimitWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_clients_keep_independent_quotas_within_one_window(self):
        limiter = InMemoryFixedWindowRateLimiter(limit=2)
        with patch("apps.api.app.middleware.rate_limit.time.time", return_value=120.0):
            results = [await limiter.hit(key) for key in ("a", "b", "a", "b", "a", "b")]
        self.assertEqual(results, [True, True, True, True, False, False])

    async def test_quota_resets_at_exact_window_boundary(self):
        limiter = InMemoryFixedWindowRateLimiter(limit=1)
        with patch("apps.api.app.middleware.rate_limit.time.time") as clock:
            clock.return_value = 179.999
            self.assertTrue(await limiter.hit("fixture-client"))
            self.assertFalse(await limiter.hit("fixture-client"))
            clock.return_value = 180.0
            self.assertTrue(await limiter.hit("fixture-client"))
            self.assertFalse(await limiter.hit("fixture-client"))

    async def test_expired_windows_do_not_accumulate_client_records(self):
        limiter = InMemoryFixedWindowRateLimiter(limit=1)
        with patch("apps.api.app.middleware.rate_limit.time.time") as clock:
            for bucket in range(100):
                clock.return_value = float(bucket * 60)
                self.assertTrue(await limiter.hit(f"fixture-client-{bucket}"))
                self.assertEqual(len(limiter._counts), 1)
        self.assertEqual(limiter._counts, {("fixture-client-99", 99): 1})

    async def test_clock_rollback_preserves_existing_future_window_quota(self):
        limiter = InMemoryFixedWindowRateLimiter(limit=1)
        with patch("apps.api.app.middleware.rate_limit.time.time") as clock:
            clock.return_value = 120.0
            self.assertTrue(await limiter.hit("future-client"))
            clock.return_value = 60.0
            self.assertTrue(await limiter.hit("earlier-client"))
            self.assertFalse(await limiter.hit("earlier-client"))
            clock.return_value = 120.0
            self.assertFalse(await limiter.hit("future-client"))

    async def test_concurrent_requests_share_the_same_client_quota(self):
        limiter = InMemoryFixedWindowRateLimiter(limit=5)
        with patch("apps.api.app.middleware.rate_limit.time.time", return_value=120.0):
            results = await asyncio.gather(*(limiter.hit("fixture-client") for _ in range(20)))
        self.assertEqual(sum(results), 5)
