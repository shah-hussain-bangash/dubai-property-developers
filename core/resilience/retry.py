"""Configurable async retries with exponential backoff and per-attempt timeouts."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from core.exceptions.errors import PlatformError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.2
    max_delay_seconds: float = 5.0
    timeout_seconds: float | None = 10.0
    jitter: bool = True

    def delay_for(self, attempt: int) -> float:
        delay = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))
        if self.jitter:
            delay *= random.uniform(0.5, 1.0)  # noqa: S311 - not security sensitive
        return delay


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, PlatformError):
        return exc.retryable
    return isinstance(exc, TimeoutError | ConnectionError)


async def retry_async(
    func: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    is_retryable: Callable[[BaseException], bool] = _is_retryable,
) -> T:
    attempt = 0
    while True:
        attempt += 1
        try:
            if policy.timeout_seconds is None:
                return await func()
            return await asyncio.wait_for(func(), timeout=policy.timeout_seconds)
        except Exception as exc:
            if attempt >= policy.max_attempts or not is_retryable(exc):
                raise
            await asyncio.sleep(policy.delay_for(attempt))
