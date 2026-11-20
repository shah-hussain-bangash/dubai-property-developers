# ruff: noqa: E402 -- Standalone audit/path bootstrap must precede application imports.
"""Factory registration tests with no environment files or real provider calls."""

import json
import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = (
    Path(sys.argv[1]).resolve()
    if __name__ == "__main__" and len(sys.argv) > 1
    else Path(__file__).resolve().parents[2]
)
if __name__ == "__main__" and len(sys.argv) > 1:
    del sys.argv[1]
sys.path.insert(0, str(ROOT))
guard = runpy.run_path(str(ROOT / "tests/unit/test_openai_responses_provider.py"))
import httpx
from pydantic import (
    SecretStr,
)

from core.config.settings import (
    Settings,
)
from core.exceptions.errors import (
    ConfigurationError,
    IntegrationError,
)
from core.llm.factory import (
    build_model_router,
)
from core.llm.openai_responses import (
    OpenAIResponsesProvider,
)


def configured(**kwargs):
    values = {
        "llm_provider": "openai",
        "llm_primary_model": "unit-primary",
        "llm_api_key": SecretStr("unit-sensitive-key"),
        "llm_max_retries": 0,
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def mocked_builder(handler):
    return patch(
        "core.llm.openai_responses.OpenAIResponsesProvider",
        side_effect=lambda *args, **kwargs: OpenAIResponsesProvider(
            *args, **kwargs, transport=httpx.MockTransport(handler)
        ),
    )


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        allowed = {
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "LOCALAPPDATA",
            "USERPROFILE",
            "COMSPEC",
            "PATHEXT",
        }
        self.clean = patch.dict(
            os.environ, {k: v for k, v in os.environ.items() if k.upper() in allowed}, clear=True
        )
        self.clean.start()
        self.addCleanup(self.clean.stop)

    async def test_mock_remains_default(self):
        settings = Settings(_env_file=None)
        self.assertEqual(settings.llm_provider, "mock")
        router = build_model_router(settings)
        response = await router.complete(guard["request"]())
        self.assertEqual(
            (router.primary.provider, router.primary.model), ("mock", "mock-deterministic")
        )
        self.assertTrue(response.is_mock)

    async def test_mock_ignores_key_and_never_constructs_openai(self):
        with patch("core.llm.openai_responses.OpenAIResponsesProvider") as constructor:
            router = build_model_router(configured(llm_provider="mock"))
            response = await router.complete(guard["request"]())
        constructor.assert_not_called()
        self.assertTrue(response.is_mock)

    async def test_openai_construction_makes_no_request(self):
        calls = []
        with mocked_builder(lambda req: calls.append(req)) as constructor:
            router = build_model_router(configured(llm_fallback_models=["unit-secondary"]))
        self.assertEqual(
            (router.primary.provider, router.primary.model), ("openai", "unit-primary")
        )
        self.assertEqual(calls, [])
        constructor.assert_called_once()
        self.assertEqual(constructor.call_args.kwargs["timeout_seconds"], 30)

    async def test_missing_key_rejected_before_construction(self):
        with patch("core.llm.openai_responses.OpenAIResponsesProvider") as constructor:  # noqa: SIM117 -- Keep fixture setup and expected-failure scopes separate for test clarity.
            with self.assertRaises(ConfigurationError):
                build_model_router(configured(llm_api_key=None))
        constructor.assert_not_called()

    async def test_default_mock_model_rejected_for_openai(self):
        with self.assertRaises(ConfigurationError):
            build_model_router(configured(llm_primary_model="mock-deterministic"))

    async def test_bad_primary_and_fallback_models_rejected(self):
        for model in ["", " ", "bad\nmodel", "mock-fallback", "/wrong-start"]:
            for field in ["llm_primary_model", "llm_fallback_models"]:
                with self.subTest(field=field), self.assertRaises(ConfigurationError):
                    build_model_router(
                        configured(**{field: [model] if field.endswith("models") else model})
                    )

    async def test_invalid_timeouts_rejected(self):
        for value in [0, -1, 121, float("nan"), float("inf")]:
            with self.subTest(value=repr(value)), self.assertRaises(ConfigurationError):
                build_model_router(configured(llm_timeout_seconds=value))

    async def test_retry_bounds_rejected(self):
        for value in [-1, 4]:
            with self.assertRaises(ConfigurationError):
                build_model_router(configured(llm_max_retries=value))

    async def test_excessive_fallback_chain_rejected(self):
        with self.assertRaises(ConfigurationError):
            build_model_router(configured(llm_fallback_models=["a", "b", "c", "d", "e"]))

    async def test_unknown_provider_not_echoed(self):
        with self.assertRaises(ConfigurationError) as caught:
            build_model_router(configured(llm_provider="unit-sensitive-provider"))
        self.assertNotIn("unit-sensitive-provider", str(caught.exception))

    async def test_registered_provider_generates_and_tracks_actual_usage(self):
        calls = []

        def handle(req):
            calls.append(json.loads(req.content))
            return httpx.Response(200, json=guard["success"]())

        with mocked_builder(handle):
            router = build_model_router(configured())
            result = await router.complete(guard["request"](), agent_id="unit-agent")
        self.assertFalse(result.is_mock)
        self.assertEqual(result.text, "Fictional response")
        self.assertEqual(calls[0]["model"], "unit-primary")
        self.assertEqual(
            router.usage_sink.totals()[("unit-agent", "unit-model-snapshot")].input_tokens, 12
        )

    async def test_explicit_fallback_stays_on_openai(self):
        calls = []

        def handle(req):
            model = json.loads(req.content)["model"]
            calls.append(model)
            return (
                httpx.Response(400, json={"error": "unit-error"})
                if model == "unit-primary"
                else httpx.Response(200, json=guard["success"]())
            )

        with mocked_builder(handle):
            result = await build_model_router(
                configured(llm_fallback_models=["unit-secondary"])
            ).complete(guard["request"]())
        self.assertEqual(calls, ["unit-primary", "unit-secondary"])
        self.assertFalse(result.is_mock)

    async def test_exhausted_real_provider_does_not_return_mock_success(self):
        calls = []

        def handle(req):
            calls.append(req)
            return httpx.Response(401, text="unit-sensitive-key")

        with mocked_builder(handle), self.assertRaises(IntegrationError):
            await build_model_router(configured()).complete(guard["request"]())
        self.assertEqual(len(calls), 1)

    async def test_rate_limit_retry_is_bounded_by_explicit_settings(self):
        calls = []

        def handle(req):
            calls.append(req)
            return (
                httpx.Response(429)
                if len(calls) == 1
                else httpx.Response(200, json=guard["success"]())
            )

        with mocked_builder(handle):
            result = await build_model_router(configured(llm_max_retries=1)).complete(
                guard["request"]()
            )
        self.assertEqual(len(calls), 2)
        self.assertFalse(result.is_mock)


if __name__ == "__main__":
    execution = unittest.main(verbosity=2, exit=False)
    assert guard["attempts"] == {"connections": 0, "held_execution": 0}
    sys.exit(0 if execution.result.wasSuccessful() else 1)
