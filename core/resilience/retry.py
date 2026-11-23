"""Configurable async retries with exponential backoff and per-attempt timeouts."""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from core.exceptions.errors import PlatformError

T = TypeVar("T")


def _valid_seconds(value: float, *, allow_zero: bool) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(value) and (value >= 0 if allow_zero else value > 0)
    except OverflowError:
        return False


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.2
    max_delay_seconds: float = 5.0
    timeout_seconds: float | None = 10.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attempts must be a positive integer")
        for name in ("base_delay_seconds", "max_delay_seconds"):
            if not _valid_seconds(getattr(self, name), allow_zero=True):
                raise ValueError(f"{name} must be finite and non-negative")
        if self.timeout_seconds is not None and not _valid_seconds(
            self.timeout_seconds, allow_zero=False
        ):
            raise ValueError("timeout_seconds must be finite and positive, or None")
        if not isinstance(self.jitter, bool):
            raise ValueError("jitter must be a boolean")

    def delay_for(self, attempt: int) -> float:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if self.base_delay_seconds == 0:
            delay = 0.0
        else:
            try:
                delay = min(
                    self.max_delay_seconds, math.ldexp(self.base_delay_seconds, attempt - 1)
                )
            except OverflowError:
                delay = self.max_delay_seconds
        if self.jitter:
            delay *= random.uniform(0.5, 1.0)  # noqa: S311 - not security sensitive
        return float(delay)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, PlatformError):
        return exc.retryable
    return isinstance(exc, TimeoutError | ConnectionError)


async def retry_async(  # noqa: UP047 -- Retain the existing shared TypeVar signature.
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
