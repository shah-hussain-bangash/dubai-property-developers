"""Integration adapters: mocks, config, and HTTP clients against httpx.MockTransport.

No real network calls are made. These tests verify request shape, auth headers,
retry behaviour and error mapping only - not live provider compatibility.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from core.config.settings import Settings
from core.exceptions.errors import IntegrationError, IntegrationNotConfiguredError
from integrations.base import IntegrationRequestRejected
from integrations.espocrm.client import EspoCRMConfig, HttpEspoCRMClient, MockEspoCRMClient
from integrations.factory import build_integrations
from integrations.google.client import MockCalendarClient
from integrations.listing_portal import PendingAccessListingPortalClient
from integrations.meta.client import HttpWhatsAppClient, MetaWhatsAppConfig
from integrations.n8n.client import HttpN8nClient, N8nConfig
from integrations.slack.client import SlackConfig, WebhookSlackNotifier
from integrations.telephony.client import MockTelephonyClient
from schemas.integrations.models import ApiAccessStatus, IntegrationMode


def test_factory_defaults_to_mock_and_describes_all(settings: Settings) -> None:
    integrations = build_integrations(settings)
    names = {d.name for d in integrations.descriptors}
    assert names == {"espocrm", "meta_whatsapp", "google", "bayut", "propertyfinder", "telephony", "n8n", "slack"}
    assert all(d.mode == IntegrationMode.MOCK for d in integrations.descriptors)
    portals = {d.name: d.api_access for d in integrations.descriptors}
    assert portals["bayut"] == ApiAccessStatus.PENDING_AUTHORIZED_ACCESS
    assert portals["propertyfinder"] == ApiAccessStatus.PENDING_AUTHORIZED_ACCESS


def test_live_mode_without_credentials_stays_mock(settings: Settings) -> None:
    integrations = build_integrations(settings.model_copy(update={"integrations_mode": "live"}))
    assert isinstance(integrations.crm, MockEspoCRMClient)


async def test_mock_crm_idempotent_create() -> None:
    crm = MockEspoCRMClient()
    a = await crm.create_lead({"lastName": "X", "emailAddress": "x@example.com"}, idempotency_key="k")
    b = await crm.create_lead({"lastName": "X", "emailAddress": "x@example.com"}, idempotency_key="k")
    assert a == b and len(crm.leads) == 1
    assert await crm.find_leads(email="x@example.com", phone=None)


async def test_mock_calendar_and_telephony() -> None:
    cal = MockCalendarClient()
    start = datetime.now(UTC)
    with pytest.raises(ValueError):
        await cal.create_event(summary="s", start=start, end=start, attendee_emails=[], description="", idempotency_key="k")
    tel = MockTelephonyClient()
    assert (await tel.request_callback(to_e164="+971500000001", reason="r", idempotency_key="k")).startswith("mock-call")


async def test_listing_portals_refuse_without_authorized_access() -> None:
    with pytest.raises(IntegrationNotConfiguredError):
        await PendingAccessListingPortalClient("bayut").fetch_leads(since=datetime.now(UTC) - timedelta(days=1))


def _espo(handler: httpx.MockTransport) -> HttpEspoCRMClient:
    cfg = EspoCRMConfig(base_url="https://crm.example.test", api_key=SecretStr("test-key"), max_attempts=3, timeout_seconds=2)
    return HttpEspoCRMClient(cfg, transport=handler)


async def test_espocrm_http_create_sends_api_key_and_retries_5xx() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "espo-1"})

    client = _espo(httpx.MockTransport(handler))
    assert await client.create_lead({"lastName": "X"}, idempotency_key="k1") == "espo-1"
    assert len(calls) == 2
    assert calls[-1].url.path == "/api/v1/Lead"
    assert calls[-1].headers["X-Api-Key"] == "test-key"


async def test_espocrm_http_4xx_is_not_retried_and_redacted() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad email demo.person@example.com")

    with pytest.raises(IntegrationRequestRejected) as info:
        await _espo(httpx.MockTransport(handler)).update_lead("1", {"x": 1})
    assert calls["n"] == 1
    assert "demo.person@example.com" not in json.dumps(info.value.details)


async def test_meta_whatsapp_http_payload_shape() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    cfg = MetaWhatsAppConfig(phone_number_id="123", access_token=SecretStr("tok"), api_version="v20.0")
    client = HttpWhatsAppClient(cfg, transport=httpx.MockTransport(handler))
    message_id = await client.send_template(
        to_e164="+971500000001", template_name="t", language_code="en", components=[], idempotency_key="k"
    )
    assert message_id == "wamid.1"
    assert captured["path"] == "/v20.0/123/messages"
    assert captured["auth"] == "Bearer tok"
    body = captured["body"]
    assert isinstance(body, dict) and body["to"] == "971500000001" and body["type"] == "template"


async def test_n8n_and_slack_http_clients() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    n8n = HttpN8nClient(N8nConfig(webhook_base_url="https://n8n.example.test"), transport=httpx.MockTransport(handler))
    await n8n.trigger("lead-created", {"id": 1}, idempotency_key="k")
    slack = WebhookSlackNotifier(
        SlackConfig(webhook_url=SecretStr("https://hooks.example.test/services/T/B/X")),
        transport=httpx.MockTransport(handler),
    )
    await slack.notify("hello", idempotency_key="k")
    assert paths == ["/webhook/lead-created", "/services/T/B/X"]


async def test_transport_errors_map_to_integration_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(IntegrationError):
        await _espo(httpx.MockTransport(handler)).get_lead("1")
