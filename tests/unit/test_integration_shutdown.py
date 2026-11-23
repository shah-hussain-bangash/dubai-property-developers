"""Runtime shutdown releases integration pools even when cleanup fails."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from pydantic import SecretStr

from integrations.espocrm.client import EspoCRMConfig, HttpEspoCRMClient
from integrations.meta.client import HttpWhatsAppClient, MetaWhatsAppConfig
from integrations.n8n.client import HttpN8nClient, N8nConfig
from integrations.slack.client import SlackConfig, WebhookSlackNotifier


class TrackingTransport(httpx.MockTransport):
    def __init__(self):
        super().__init__(lambda request: httpx.Response(200, json={"ok": True}))
        self.close_count = 0

    async def aclose(self):
        self.close_count += 1


class HttpAdapterShutdownTests(unittest.IsolatedAsyncioTestCase):
    def make_adapters(self):
        constructors = (
            (
                HttpEspoCRMClient,
                EspoCRMConfig(base_url="https://crm.example.test", api_key=SecretStr("fixture")),
            ),
            (
                HttpWhatsAppClient,
                MetaWhatsAppConfig(phone_number_id="fixture", access_token=SecretStr("fixture")),
            ),
            (HttpN8nClient, N8nConfig(webhook_base_url="https://n8n.example.test")),
            (
                WebhookSlackNotifier,
                SlackConfig(webhook_url=SecretStr("https://hooks.example.test/services/demo")),
            ),
        )
        for constructor, config in constructors:
            transport = TrackingTransport()
            adapter = constructor(config, transport=transport)
            self.addAsyncCleanup(adapter._http.aclose)
            yield adapter, transport

    async def test_every_http_adapter_releases_its_owned_transport(self):
        for adapter, transport in self.make_adapters():
            with self.subTest(adapter=type(adapter).__name__):
                await adapter.aclose()
                self.assertEqual(transport.close_count, 1)
                self.assertTrue(adapter._http._client.is_closed)

    async def test_repeated_adapter_cleanup_is_safe(self):
        for adapter, transport in self.make_adapters():
            with self.subTest(adapter=type(adapter).__name__):
                await adapter.aclose()
                await adapter.aclose()
                self.assertEqual(transport.close_count, 1)


class IntegrationSetShutdownTests(unittest.IsolatedAsyncioTestCase):
    def make_set(self, clients):
        from integrations.factory import IntegrationSet

        return IntegrationSet(
            crm=clients[0],
            whatsapp=clients[1],
            calendar=clients[2],
            bayut=clients[3],
            propertyfinder=clients[4],
            telephony=clients[5],
            n8n=clients[6],
            slack=clients[7],
        )

    async def test_mock_only_set_requires_no_cleanup_methods(self):
        await self.make_set([object() for _ in range(8)]).aclose()

    async def test_every_resource_owner_is_closed(self):
        clients = [SimpleNamespace(aclose=AsyncMock()) for _ in range(8)]
        await self.make_set(clients).aclose()
        for client in clients:
            client.aclose.assert_awaited_once()

    async def test_one_cleanup_failure_does_not_skip_other_clients(self):
        clients = [SimpleNamespace(aclose=AsyncMock()) for _ in range(8)]
        clients[5].aclose.side_effect = RuntimeError("fixture cleanup failure")
        with self.assertRaisesRegex(RuntimeError, "fixture cleanup failure"):
            await self.make_set(clients).aclose()
        for client in clients:
            client.aclose.assert_awaited_once()


class RuntimeShutdownTests(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self):
        from core.config.settings import Environment, Settings
        from workflows.runtime import build_runtime

        runtime = build_runtime(
            Settings(
                _env_file=None,
                environment=Environment.TEST,
                integrations_mode="mock",
                llm_provider="mock",
                lead_store_backend="memory",
                workflow_store_backend="memory",
            )
        )
        runtime.integrations = SimpleNamespace(aclose=AsyncMock())
        runtime._db_engine = SimpleNamespace(dispose=AsyncMock())
        runtime._initialized = True
        return runtime

    async def test_shutdown_closes_integrations_and_database(self):
        runtime = self.make_runtime()
        integrations, engine = runtime.integrations, runtime._db_engine
        await runtime.shutdown()
        integrations.aclose.assert_awaited_once()
        engine.dispose.assert_awaited_once()
        self.assertIsNone(runtime._db_engine)
        self.assertFalse(runtime._initialized)

    async def test_integration_failure_still_releases_database_and_resets_state(self):
        runtime = self.make_runtime()
        engine = runtime._db_engine
        runtime.integrations.aclose.side_effect = RuntimeError("fixture integration failure")
        with self.assertRaisesRegex(RuntimeError, "fixture integration failure"):
            await runtime.shutdown()
        engine.dispose.assert_awaited_once()
        self.assertIsNone(runtime._db_engine)
        self.assertFalse(runtime._initialized)

    async def test_database_failure_still_closes_integrations_and_resets_state(self):
        runtime = self.make_runtime()
        runtime._db_engine.dispose.side_effect = RuntimeError("fixture database failure")
        with self.assertRaisesRegex(RuntimeError, "fixture database failure"):
            await runtime.shutdown()
        runtime.integrations.aclose.assert_awaited_once()
        self.assertFalse(runtime._initialized)
