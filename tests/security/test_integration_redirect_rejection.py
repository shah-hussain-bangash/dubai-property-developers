"""Redirect responses must not acknowledge delivery or forward credentials."""

import secrets
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from core.resilience.retry import RetryPolicy
from integrations.base import BearerTokenAuth, HttpIntegrationClient, IntegrationRequestRejected
from integrations.slack.client import SlackConfig, WebhookSlackNotifier


@pytest.mark.parametrize("status", [300, 301, 302, 303, 304, 307, 308])
@pytest.mark.parametrize("expect_json", [True, False])
async def test_redirect_is_rejected_without_retry_follow_or_body_leak(status, expect_json):
    requests = []
    token = secrets.token_hex(16)

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            headers={"Location": f"https://other.example.test/target?token={token}"},
            json={"id": "fictional-success", "token": token},
        )

    client = HttpIntegrationClient(
        integration="fictional",
        base_url="https://integration.example.test",
        auth=BearerTokenAuth(SecretStr(token)),
        retry_policy=RetryPolicy(max_attempts=3),
        transport=httpx.MockTransport(handler),
    )
    try:
        with (
            patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep,
            pytest.raises(IntegrationRequestRejected) as rejected,
        ):
            await client.request("POST", "/hook", expect_json=expect_json)
        assert len(requests) == 1
        assert requests[0].url.host == "integration.example.test"
        assert requests[0].headers["Authorization"] == f"Bearer {token}"
        assert rejected.value.retryable is False
        assert rejected.value.details == {"status": status}
        assert token not in str(rejected.value)
        sleep.assert_not_awaited()
    finally:
        await client.aclose()


async def test_empty_slack_redirect_does_not_acknowledge_notification():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.test/login"})

    client = WebhookSlackNotifier(
        SlackConfig(webhook_url=SecretStr("https://hooks.example.test/services/fictional")),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(IntegrationRequestRejected):
            await client.notify("Fictional staff alert", idempotency_key="fictional")
        assert len(requests) == 1
    finally:
        await client.aclose()


async def test_transient_retry_stops_when_provider_redirects():
    responses = [httpx.Response(503), httpx.Response(307), httpx.Response(200, json={"ok": True})]
    client = HttpIntegrationClient(
        integration="fictional",
        base_url="https://integration.example.test",
        auth=BearerTokenAuth(SecretStr(secrets.token_hex(16))),
        retry_policy=RetryPolicy(max_attempts=3),
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )
    try:
        with (
            patch("core.resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep,
            pytest.raises(IntegrationRequestRejected) as rejected,
        ):
            await client.request("POST", "/hook")
        assert rejected.value.details == {"status": 307}
        assert len(responses) == 1
        sleep.assert_awaited_once()
    finally:
        await client.aclose()
