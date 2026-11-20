from __future__ import annotations

import asyncio

import pytest

from core.exceptions.errors import IntegrationError, NotFoundError
from core.llm.mock import MockLLMProvider
from core.llm.router import ModelRouter, ModelTarget
from core.llm.types import ChatMessage, ChatRole, LLMRequest
from core.observability.usage import InMemoryUsageTracker
from core.resilience.idempotency import InMemoryIdempotencyStore, make_idempotency_key
from core.resilience.retry import RetryPolicy, retry_async

FAST = RetryPolicy(max_attempts=3, base_delay_seconds=0, timeout_seconds=1, jitter=False)


async def test_retry_recovers_from_transient_errors() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert await retry_async(flaky, FAST) == "ok"
    assert calls["n"] == 3


async def test_retry_does_not_retry_non_retryable() -> None:
    calls = {"n": 0}

    async def missing() -> None:
        calls["n"] += 1
        raise NotFoundError("nope")

    with pytest.raises(NotFoundError):
        await retry_async(missing, FAST)
    assert calls["n"] == 1


async def test_retry_times_out() -> None:
    async def slow() -> None:
        await asyncio.sleep(5)

    with pytest.raises(TimeoutError):
        await retry_async(slow, RetryPolicy(max_attempts=1, timeout_seconds=0.05))


async def test_idempotency_keys_are_stable_and_scoped() -> None:
    a = make_idempotency_key("send", {"x": 1, "y": 2}, scope="t1")
    b = make_idempotency_key("send", {"y": 2, "x": 1}, scope="t1")
    c = make_idempotency_key("send", {"x": 1, "y": 2}, scope="t2")
    assert a == b != c
    store = InMemoryIdempotencyStore()
    await store.put(a, {"id": 1}, ttl_seconds=60)
    assert await store.get(a) == {"id": 1}


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[ChatMessage(role=ChatRole.USER, content="hello there")], metadata={"task": "t"}
    )


async def test_router_falls_back_and_tracks_usage() -> None:
    tracker = InMemoryUsageTracker()
    router = ModelRouter(
        {"bad": MockLLMProvider(fail_times=99), "good": MockLLMProvider({"t": "scripted answer"})},
        [ModelTarget("bad", "m1"), ModelTarget("good", "m2")],
        retry_policy=FAST,
        usage_sink=tracker,
    )
    response = await router.complete(_request(), agent_id="tester")
    assert response.text == "scripted answer"
    assert response.model == "m2"
    assert response.is_mock
    assert tracker.totals()[("tester", "m2")].total_tokens > 0


async def test_router_raises_when_all_targets_fail() -> None:
    router = ModelRouter(
        {"bad": MockLLMProvider(fail_times=99)}, [ModelTarget("bad", "m1")], retry_policy=FAST
    )
    with pytest.raises(IntegrationError):
        await router.complete(_request())
