# ruff: noqa: E402 -- Standalone audit/path bootstrap must precede application imports.
"""Local Ollama contracts, simulated HTTP only; no model download or generation."""

import asyncio
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
import contextlib

import httpx

from core.config.settings import (
    Settings,
)
from core.exceptions.errors import (
    ConfigurationError,
    DomainValidationError,
    IntegrationError,
    IntegrationNotConfiguredError,
)
from core.llm.factory import (
    build_model_router,
)
from core.llm.ollama_local import (
    OllamaLocalProvider,
)
from core.llm.types import (
    ChatMessage,
    LLMRequest,
)


def success():
    return {
        "model": "qwen3:8b",
        "done": True,
        "done_reason": "stop",
        "message": {"role": "assistant", "content": "Fictional local response"},
        "prompt_eval_count": 20,
        "eval_count": 4,
    }


def provider(handler):
    return OllamaLocalProvider(transport=httpx.MockTransport(handler))


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
        clean = patch.dict(
            os.environ, {k: v for k, v in os.environ.items() if k.upper() in allowed}, clear=True
        )
        clean.start()
        self.addCleanup(clean.stop)

    async def test_success_real_text_and_usage(self):
        result = await provider(lambda req: httpx.Response(200, json=success())).complete(
            guard["request"](), model="qwen3:8b"
        )
        self.assertEqual(
            (result.text, result.provider, result.model),
            ("Fictional local response", "ollama", "qwen3:8b"),
        )
        self.assertEqual(
            (result.input_tokens, result.output_tokens, result.is_mock), (20, 4, False)
        )

    async def test_fixed_local_endpoint_no_key_no_metadata_and_ordered_roles(self):
        calls = []

        def handle(req):
            calls.append(req)
            return httpx.Response(200, json=success())

        messages = [
            ChatMessage(role="system", content="Fictional rules"),
            ChatMessage(role="user", content="مرحبا"),
        ]
        await provider(handle).complete(
            LLMRequest(messages=messages, metadata={"private": "omit"}), model="qwen3:8b"
        )
        req = calls[0]
        body = json.loads(req.content)
        self.assertEqual((req.method, str(req.url)), ("POST", "http://127.0.0.1:11434/api/chat"))
        self.assertNotIn("authorization", req.headers)
        self.assertEqual(
            body["messages"], [{"role": m.role.value, "content": m.content} for m in messages]
        )
        self.assertFalse(body["stream"])
        self.assertFalse(body["think"])
        self.assertEqual(body["options"], {"temperature": 0.2, "num_predict": 800, "num_ctx": 4096})
        self.assertNotIn("metadata", body)
        self.assertNotIn("tools", body)

    async def test_invalid_cloud_models_and_inputs_rejected_before_http(self):
        calls = []
        p = provider(lambda req: calls.append(req))
        for model in ["qwen3:8b-cloud", "gpt-4.1-mini", "", "mock-deterministic"]:
            with self.assertRaises(DomainValidationError):
                await p.complete(guard["request"](), model=model)
        for req in [
            LLMRequest(messages=[]),
            LLMRequest(messages=[ChatMessage(role="user", content=" ")]),
            LLMRequest(messages=[ChatMessage(role="user", content="x" * 8001)]),
            guard["request"](max_output_tokens=2049),
            guard["request"](temperature=float("nan")),
        ]:
            with self.assertRaises(DomainValidationError):
                await p.complete(req, model="qwen3:8b")
        self.assertEqual(calls, [])

    async def test_timeout_configuration_bounded(self):
        for value in [0, -1, 181, True, float("nan"), float("inf")]:
            with self.assertRaises(ConfigurationError):
                OllamaLocalProvider(timeout_seconds=value)

    async def test_http_errors_not_retried_or_echoed(self):
        for status in [302, 404, 429, 500]:
            calls = []

            def handle(req, *, calls=calls, status=status):
                calls.append(req)
                return httpx.Response(
                    status,
                    text="private upstream text",
                    headers={"location": "https://external.invalid"},
                )

            expected = IntegrationNotConfiguredError if status == 404 else IntegrationError
            with self.assertRaises(expected) as caught:
                await provider(handle).complete(guard["request"](), model="qwen3:8b")
            self.assertEqual(len(calls), 1)
            self.assertNotIn("private upstream text", str(caught.exception))

    async def test_partial_tool_empty_and_bad_usage_rejected(self):
        for change in [
            {"done": False},
            {"done_reason": "length"},
            {"model": "other"},
            {"message": {"role": "assistant", "content": ""}},
            {"message": {"role": "assistant", "content": "partial", "tool_calls": [{}]}},
            {"prompt_eval_count": True},
            {"eval_count": -1},
            {"error": "private error"},
        ]:
            body = {**success(), **change}
            with self.assertRaises(IntegrationError):
                await provider(lambda req, body=body: httpx.Response(200, json=body)).complete(
                    guard["request"](), model="qwen3:8b"
                )

    async def test_bad_json_content_type_and_size_rejected(self):
        for response in [
            httpx.Response(200, content=b"{", headers={"content-type": "application/json"}),
            httpx.Response(200, text="plain text"),
            httpx.Response(
                200,
                content=b"x" * (2 * 1024 * 1024 + 1),
                headers={"content-type": "application/json"},
            ),
        ]:
            with self.assertRaises(IntegrationError):
                await provider(lambda req, response=response: response).complete(
                    guard["request"](), model="qwen3:8b"
                )

    async def test_timeout_sanitized_and_cancellation_propagates(self):
        def timeout(req):
            raise httpx.ReadTimeout("private detail", request=req)

        with self.assertRaises(IntegrationError) as caught:
            await provider(timeout).complete(guard["request"](), model="qwen3:8b")
        self.assertNotIn("private detail", str(caught.exception))

        async def cancel(req):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await provider(cancel).complete(guard["request"](), model="qwen3:8b")

    async def test_resources_closed_on_success_and_error(self):
        class Transport(httpx.MockTransport):
            closed = False

            async def aclose(self):
                self.closed = True

        for status in [200, 500]:
            transport = Transport(lambda req, status=status: httpx.Response(status, json=success()))
            with contextlib.suppress(IntegrationError):
                await OllamaLocalProvider(transport=transport).complete(
                    guard["request"](), model="qwen3:8b"
                )
            self.assertTrue(transport.closed)

    async def test_mock_default_does_not_construct_local_provider(self):
        with patch("core.llm.ollama_local.OllamaLocalProvider") as constructor:
            result = await build_model_router(Settings(_env_file=None)).complete(guard["request"]())
        constructor.assert_not_called()
        self.assertTrue(result.is_mock)

    async def test_factory_selects_local_provider_without_key(self):
        calls = []

        def handle(req):
            calls.append(req)
            return httpx.Response(200, json=success())

        with patch(
            "core.llm.ollama_local.OllamaLocalProvider",
            side_effect=lambda **kw: OllamaLocalProvider(
                **kw, transport=httpx.MockTransport(handle)
            ),
        ):
            router = build_model_router(
                Settings(
                    _env_file=None,
                    llm_provider="ollama",
                    llm_primary_model="qwen3:8b",
                    llm_max_retries=0,
                )
            )
            self.assertEqual(calls, [])
            result = await router.complete(guard["request"]())
        self.assertEqual(router.primary.provider, "ollama")
        self.assertFalse(result.is_mock)
        self.assertEqual(len(calls), 1)

    async def test_factory_rejects_unconfigured_or_cloud_models(self):
        for values in [
            {"llm_primary_model": "mock-deterministic"},
            {"llm_primary_model": "qwen3:8b-cloud"},
            {"llm_fallback_models": ["other"]},
            {"llm_timeout_seconds": 181},
            {"llm_max_retries": 3},
        ]:
            settings = {
                "llm_provider": "ollama",
                "llm_primary_model": "qwen3:8b",
                "llm_max_retries": 0,
                **values,
            }
            with self.assertRaises(ConfigurationError):
                build_model_router(Settings(_env_file=None, **settings))


if __name__ == "__main__":
    execution = unittest.main(verbosity=2, exit=False)
    assert guard["attempts"] == {"connections": 0, "held_execution": 0}
    sys.exit(0 if execution.result.wasSuccessful() else 1)
