"""Caller-owned configuration collections cannot change an existing router."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.llm.router import ModelRouter, ModelTarget
from core.llm.types import ChatMessage, ChatRole, LLMRequest, LLMResponse
from core.resilience.retry import RetryPolicy


def fixture_request():
    return LLMRequest(
        messages=[ChatMessage(role=ChatRole.USER, content="Fictional fixture prompt")]
    )


def fixture_provider(name):
    return SimpleNamespace(
        name=name,
        complete=AsyncMock(
            return_value=LLMResponse(text="Fictional fixture answer", provider=name, model=name)
        ),
    )


def fixture_router(providers, chain):
    return ModelRouter(
        providers,
        chain,
        retry_policy=RetryPolicy(max_attempts=1, timeout_seconds=1),
    )


class ModelRouterConfigurationSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_clearing_caller_chain_keeps_primary_and_execution(self):
        provider = fixture_provider("fixture-original")
        chain = [ModelTarget("fixture", "fixture-original")]
        router = fixture_router({"fixture": provider}, chain)
        chain.clear()

        self.assertEqual(router.primary, ModelTarget("fixture", "fixture-original"))
        response = await router.complete(fixture_request())

        self.assertEqual(response.model, "fixture-original")
        provider.complete.assert_awaited_once()

    async def test_replacing_provider_mapping_cannot_redirect_existing_router(self):
        original = fixture_provider("fixture-original")
        replacement = fixture_provider("fixture-replacement")
        providers = {"fixture": original}
        router = fixture_router(providers, [ModelTarget("fixture", "fixture-original")])
        providers["fixture"] = replacement

        response = await router.complete(fixture_request())

        self.assertEqual(response.provider, "fixture-original")
        original.complete.assert_awaited_once()
        replacement.complete.assert_not_awaited()

    async def test_active_request_keeps_fallback_after_caller_configuration_edits(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def wait_then_fail(request, *, model):
            started.set()
            await release.wait()
            raise ValueError("Fictional provider failure")

        primary = SimpleNamespace(name="primary", complete=AsyncMock(side_effect=wait_then_fail))
        fallback = fixture_provider("fixture-fallback")
        providers = {"primary": primary, "fallback": fallback}
        chain = [
            ModelTarget("primary", "fixture-primary"),
            ModelTarget("fallback", "fixture-fallback"),
        ]
        router = fixture_router(providers, chain)
        task = asyncio.create_task(router.complete(fixture_request()))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            providers.clear()
            chain.clear()
        finally:
            release.set()

        response = await asyncio.wait_for(task, timeout=1)

        self.assertEqual(response.provider, "fixture-fallback")
        fallback.complete.assert_awaited_once()

    async def test_new_router_can_use_deliberately_revised_configuration(self):
        original = fixture_provider("fixture-original")
        revised = fixture_provider("fixture-revised")
        providers = {"fixture": original}
        chain = [ModelTarget("fixture", "fixture-original")]
        first = fixture_router(providers, chain)
        providers["fixture"] = revised
        chain[0] = ModelTarget("fixture", "fixture-revised")
        second = fixture_router(providers, chain)

        first_request = fixture_request()
        first_request.model = "fixture-original"
        second_request = fixture_request()
        second_request.model = "fixture-revised"
        first_response = await first.complete(first_request)
        second_response = await second.complete(second_request)

        self.assertEqual(first_response.model, "fixture-original")
        self.assertEqual(second_response.model, "fixture-revised")
        self.assertEqual(first.primary.model, "fixture-original")
        self.assertEqual(second.primary.model, "fixture-revised")
        original.complete.assert_awaited_once()
        revised.complete.assert_awaited_once()
        self.assertEqual(original.complete.call_args.kwargs["model"], "fixture-original")
        self.assertEqual(revised.complete.call_args.kwargs["model"], "fixture-revised")
