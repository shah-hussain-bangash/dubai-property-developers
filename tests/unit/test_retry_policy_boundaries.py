"""Retry policies reject unusable values and cap backoff without overflow."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from core.resilience.retry import RetryPolicy, retry_async


class RetryPolicyValidationTests(unittest.TestCase):
    def test_attempt_limits_must_be_positive_integers(self):
        for value in (0, -1, True, False, 1.5, "3", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "max_attempts"):
                RetryPolicy(max_attempts=value)

    def test_delay_values_must_be_finite_and_non_negative(self):
        for name in ("base_delay_seconds", "max_delay_seconds"):
            for value in (-1, float("nan"), float("inf"), -float("inf"), True, "1", 10**400):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaisesRegex(ValueError, name),
                ):
                    RetryPolicy(**{name: value})

    def test_timeout_must_be_positive_finite_or_disabled(self):
        for value in (0, -1, float("nan"), float("inf"), True, "1", 10**400):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "timeout_seconds"):
                RetryPolicy(timeout_seconds=value)
        self.assertIsNone(RetryPolicy(timeout_seconds=None).timeout_seconds)

    def test_jitter_requires_a_boolean(self):
        for value in (0, 1, "false", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "jitter"):
                RetryPolicy(jitter=value)

    def test_delay_attempt_must_be_a_positive_integer(self):
        policy = RetryPolicy(jitter=False)
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "attempt"):
                policy.delay_for(value)


class RetryBackoffTests(unittest.TestCase):
    def test_ordinary_exponential_delays_keep_their_existing_values(self):
        policy = RetryPolicy(base_delay_seconds=0.25, max_delay_seconds=1, jitter=False)
        self.assertEqual([policy.delay_for(n) for n in range(1, 6)], [0.25, 0.5, 1, 1, 1])

    def test_large_attempts_saturate_at_the_cap_without_overflow(self):
        policy = RetryPolicy(base_delay_seconds=0.2, max_delay_seconds=5, jitter=False)
        for attempt in (1025, 4096, 10000):
            with self.subTest(attempt=attempt):
                self.assertEqual(policy.delay_for(attempt), 5.0)

    def test_zero_delays_remain_supported_even_for_large_attempts(self):
        for policy in (
            RetryPolicy(base_delay_seconds=0, jitter=False),
            RetryPolicy(max_delay_seconds=0, jitter=False),
        ):
            with self.subTest(policy=policy):
                self.assertEqual(policy.delay_for(10000), 0.0)

    def test_jitter_is_applied_after_the_delay_cap(self):
        policy = RetryPolicy(base_delay_seconds=1, max_delay_seconds=5, jitter=True)
        with patch("core.resilience.retry.random.uniform", return_value=0.5) as uniform:
            self.assertEqual(policy.delay_for(10000), 2.5)
        uniform.assert_called_once_with(0.5, 1.0)


class RetryExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_errors_recover_with_expected_delays(self):
        operation = AsyncMock(
            side_effect=[ConnectionError("fixture"), ConnectionError("fixture"), "ok"]
        )
        policy = RetryPolicy(
            max_attempts=3, base_delay_seconds=0.25, timeout_seconds=None, jitter=False
        )
        with patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            self.assertEqual(await retry_async(operation, policy), "ok")
        self.assertEqual(operation.await_count, 3)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [0.25, 0.5])

    async def test_exhausted_policy_stops_at_its_attempt_limit(self):
        operation = AsyncMock(side_effect=ConnectionError("fixture"))
        with (
            patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep,
            self.assertRaises(ConnectionError),
        ):
            await retry_async(operation, RetryPolicy(max_attempts=2, timeout_seconds=None))
        self.assertEqual(operation.await_count, 2)
        sleep.assert_awaited_once()

    async def test_cancellation_is_never_retried(self):
        for timeout in (None, 1):
            with self.subTest(timeout=timeout):
                operation = AsyncMock(side_effect=asyncio.CancelledError)
                with (
                    patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep,
                    self.assertRaises(asyncio.CancelledError),
                ):
                    await retry_async(operation, RetryPolicy(timeout_seconds=timeout))
                operation.assert_awaited_once()
                sleep.assert_not_awaited()
