"""Retries and fallbacks use independent copies of the original model request."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.llm.router import ModelRouter, ModelTarget
from core.llm.types import ChatMessage, ChatRole, LLMRequest, LLMResponse
from core.resilience.retry import RetryPolicy


def fixture_request():
    return LLMRequest(
        messages=[ChatMessage(role=ChatRole.USER, content="Fictional fixture prompt")],
        metadata={"fixture": {"labels": ["original"]}},
    )


def fixture_response(model):
    return LLMResponse(text="Fictional fixture answer", provider="fixture", model=model)


def mutate(request):
    request.messages[0].content = "Changed fixture prompt"
    request.metadata["fixture"]["labels"].append("changed")
    request.temperature = 1.5
    request.max_output_tokens = 10


def fixture_router(primary, fallback=None, *, attempts=1):
    providers = {"primary": SimpleNamespace(name="primary", complete=primary)}
    chain = [ModelTarget("primary", "fixture-primary")]
    if fallback is not None:
        providers["fallback"] = SimpleNamespace(name="fallback", complete=fallback)
        chain.append(ModelTarget("fallback", "fixture-fallback"))
    return ModelRouter(
        providers,
        chain,
        retry_policy=RetryPolicy(
            max_attempts=attempts, base_delay_seconds=0, timeout_seconds=1, jitter=False
        ),
    )


class ModelRouterRequestSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_provider_cannot_change_fallback_request_or_caller(self):
        request = fixture_request()
        original = request.model_dump()

        async def fail_after_mutation(value, *, model):
            mutate(value)
            raise ValueError("Fictional provider failure")

        fallback = AsyncMock(return_value=fixture_response("fixture-fallback"))
        router = fixture_router(AsyncMock(side_effect=fail_after_mutation), fallback)

        response = await router.complete(request)

        self.assertEqual(fallback.call_args.args[0].model_dump(), original)
        self.assertEqual(request.model_dump(), original)
        self.assertEqual(response.model, "fixture-fallback")

    async def test_retry_receives_original_request_after_provider_mutation(self):
        request = fixture_request()
        original = request.model_dump()
        observed = []

        async def retry_once(value, *, model):
            observed.append(value.model_dump())
            if len(observed) == 1:
                mutate(value)
                raise ConnectionError("Fictional transient failure")
            return fixture_response(model)

        router = fixture_router(AsyncMock(side_effect=retry_once), attempts=2)

        await router.complete(request)

        self.assertEqual(observed, [original, original])
        self.assertEqual(request.model_dump(), original)

    async def test_caller_changes_while_waiting_do_not_change_fallback_request(self):
        request = fixture_request()
        original = request.model_dump()
        started, release = asyncio.Event(), asyncio.Event()

        async def wait_then_fail(value, *, model):
            started.set()
            await release.wait()
            raise ValueError("Fictional provider failure")

        fallback = AsyncMock(return_value=fixture_response("fixture-fallback"))
        router = fixture_router(AsyncMock(side_effect=wait_then_fail), fallback)
        task = asyncio.create_task(router.complete(request))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            mutate(request)
        finally:
            release.set()
        await asyncio.wait_for(task, timeout=1)

        self.assertEqual(fallback.call_args.args[0].model_dump(), original)
        self.assertEqual(request.messages[0].content, "Changed fixture prompt")

    async def test_successful_provider_cannot_mutate_caller_and_usage_is_recorded(self):
        request = fixture_request()
        original = request.model_dump()

        async def succeed_after_mutation(value, *, model):
            mutate(value)
            return LLMResponse(
                text="Fictional fixture answer",
                provider="fixture",
                model=model,
                input_tokens=3,
                output_tokens=2,
            )

        router = fixture_router(AsyncMock(side_effect=succeed_after_mutation))

        response = await router.complete(request, agent_id="fixture-agent")

        self.assertEqual(request.model_dump(), original)
        self.assertEqual(response.text, "Fictional fixture answer")
        totals = router.usage_sink.totals()
        self.assertEqual(totals[("fixture-agent", "fixture-primary")].total_tokens, 5)
