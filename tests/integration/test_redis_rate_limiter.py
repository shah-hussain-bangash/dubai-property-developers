"""Real Redis validates atomic fixed-window rate-limit counters and expiry."""

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
import redis.asyncio as redis_asyncio

from apps.api.app.middleware.rate_limit import RedisFixedWindowRateLimiter

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Integration tests disabled",
    ),
]


@pytest.fixture
async def limiter_case(monkeypatch):
    client = redis_asyncio.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    case = SimpleNamespace(
        client=client,
        key="test:rate-limit:" + uuid.uuid4().hex,
        clock=1700000000.0,
        keys=[],
    )
    monkeypatch.setattr("apps.api.app.middleware.rate_limit.time.time", lambda: case.clock)
    case.redis_key = f"ratelimit:{case.key}:{int(case.clock // 60)}"
    case.keys.append(case.redis_key)
    try:
        await client.ping()
        yield case
    finally:
        try:
            await client.delete(*case.keys)
        finally:
            await client.aclose()


async def test_concurrent_requests_respect_limit_and_always_leave_expiry(limiter_case):
    case = limiter_case
    limiter = RedisFixedWindowRateLimiter(case.client, limit=5)
    results = await asyncio.gather(*(limiter.hit(case.key) for _ in range(20)))
    assert sum(results) == 5
    assert int(await case.client.get(case.redis_key)) == 20
    assert 0 < await case.client.ttl(case.redis_key) <= 60


async def test_existing_counter_without_expiry_is_repaired(limiter_case):
    case = limiter_case
    await case.client.set(case.redis_key, 4)
    limiter = RedisFixedWindowRateLimiter(case.client, limit=5)
    assert await case.client.ttl(case.redis_key) == -1
    assert await limiter.hit(case.key) is True
    assert 0 < await case.client.ttl(case.redis_key) <= 60
    assert await limiter.hit(case.key) is False


async def test_existing_expiry_is_not_extended_on_later_hits(limiter_case):
    case = limiter_case
    await case.client.set(case.redis_key, 1, px=15000)
    before = await case.client.pttl(case.redis_key)
    limiter = RedisFixedWindowRateLimiter(case.client, limit=5)
    assert await limiter.hit(case.key) is True
    assert 0 < await case.client.pttl(case.redis_key) <= before


async def test_next_window_starts_with_a_fresh_counter(limiter_case):
    case = limiter_case
    limiter = RedisFixedWindowRateLimiter(case.client, limit=1)
    assert await limiter.hit(case.key) is True
    assert await limiter.hit(case.key) is False
    case.clock += 60
    new_key = f"ratelimit:{case.key}:{int(case.clock // 60)}"
    case.keys.append(new_key)
    assert await limiter.hit(case.key) is True
    assert int(await case.client.get(case.redis_key)) == 2
    assert int(await case.client.get(new_key)) == 1
    assert 0 < await case.client.ttl(new_key) <= 60


async def test_clients_have_independent_request_quotas(limiter_case):
    case = limiter_case
    other = case.key + ":other"
    case.keys.append(f"ratelimit:{other}:{int(case.clock // 60)}")
    limiter = RedisFixedWindowRateLimiter(case.client, limit=1)
    assert await limiter.hit(case.key) is True
    assert await limiter.hit(other) is True
    assert await limiter.hit(case.key) is False
