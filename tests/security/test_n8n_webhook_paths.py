"""Webhook paths cannot escape the webhook prefix or change the requested workflow."""

import json

import httpx
import pytest

from core.exceptions.errors import DomainValidationError
from integrations.n8n.client import HttpN8nClient, MockN8nClient, N8nConfig

UNSAFE_PATHS = [
    "",
    "/",
    ".",
    "..",
    "../rest/settings",
    "folder/../../rest/settings",
    "folder/../other-workflow",
    "folder//workflow",
    "folder\\other",
    "%2e%2e/rest/settings",
    "%252e%252e/rest/settings",
    "workflow?mode=other",
    "workflow#other",
    "workflow\n",
    "workflow\x00",
    "two names",
    "workflow\uff0fother",
    "a" * 1025,
    None,
    123,
    ["workflow"],
]


@pytest.mark.parametrize("path", UNSAFE_PATHS)
@pytest.mark.parametrize("adapter", ["http", "mock"])
async def test_unsafe_paths_fail_before_any_workflow_is_triggered(path, adapter):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"accepted": True})

    client = (
        HttpN8nClient(
            N8nConfig(webhook_base_url="https://n8n.example.test"),
            transport=httpx.MockTransport(handler),
        )
        if adapter == "http"
        else MockN8nClient()
    )
    try:
        with pytest.raises(DomainValidationError, match="Webhook path"):
            await client.trigger(path, {"fictional": True}, idempotency_key="fictional")
        assert requests == []
        if adapter == "mock":
            assert client.triggered == []
    finally:
        if adapter == "http":
            await client.aclose()


@pytest.mark.parametrize(
    "path,normalized",
    [
        ("lead-created", "lead-created"),
        ("team/lead-created", "team/lead-created"),
        ("/team/lead-created/", "team/lead-created"),
        ("workflow.v1/record_123", "workflow.v1/record_123"),
        ("a" * 1024, "a" * 1024),
    ],
)
async def test_valid_webhook_routes_preserve_payload_and_key(path, normalized):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"accepted": True})

    client = HttpN8nClient(
        N8nConfig(webhook_base_url="https://n8n.example.test/automation"),
        transport=httpx.MockTransport(handler),
    )
    payload = {"fictional_enquiry": "portfolio-only"}
    try:
        result = await client.trigger(path, payload, idempotency_key="fictional")
        assert result == {"accepted": True}
        assert len(requests) == 1
        request = requests[0]
        assert request.method == "POST"
        assert request.url.path == f"/automation/webhook/{normalized}"
        assert request.url.query == b""
        assert request.url.fragment == ""
        assert request.headers["Idempotency-Key"] == "fictional"
        assert json.loads(request.content) == payload

        mock = MockN8nClient()
        assert await mock.trigger(path, payload, idempotency_key="fictional") == {
            "accepted": True,
            "is_mock": True,
        }
        assert mock.triggered == [{"path": normalized, "payload": payload, "key": "fictional"}]
    finally:
        await client.aclose()
