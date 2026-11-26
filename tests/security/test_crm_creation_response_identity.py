"""Malformed provider acknowledgements cannot become successful CRM creations."""

import secrets
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from core.exceptions.errors import DomainValidationError
from integrations.espocrm.client import EspoCRMConfig, HttpEspoCRMClient
from tools.base import ToolCallContext

BAD_IDS = [None, True, 123, "", " ", "../other", "record?query", "x" * 129]


@pytest.mark.parametrize("body", [None, [], "fictional", {}, *({"id": v} for v in BAD_IDS)])
@pytest.mark.parametrize("operation", ["lead", "note"])
async def test_http_creation_rejects_malformed_acknowledgements(body, operation):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    client = HttpEspoCRMClient(
        EspoCRMConfig(
            base_url="https://crm.example.test", api_key=SecretStr(secrets.token_hex(16))
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(DomainValidationError):
            if operation == "lead":
                await client.create_lead(
                    {"lastName": "Fictional visitor"}, idempotency_key="fixture"
                )
            else:
                await client.add_note(
                    parent_type="Lead", parent_id="fixture", text="Fictional note"
                )
        # A malformed acknowledgement does not trigger another creation request.
        assert len(requests) == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("operation", ["create_lead", "add_note"])
@pytest.mark.parametrize("identifier", BAD_IDS)
async def test_gateway_does_not_cache_invalid_creation_identity(
    runtime, manager, monkeypatch, operation, identifier
):
    client = runtime.integrations.crm
    provider = AsyncMock(side_effect=[identifier, "fictional-valid-123"])
    monkeypatch.setattr(client, operation, provider)
    tool_name = f"crm.{operation}"
    context = ToolCallContext(
        manager, manager.tenant_id, "fictional-create-response", "crm", frozenset({tool_name})
    )
    payload = (
        {
            "local_lead_id": "fictional-source",
            "data": {"lastName": "Fictional visitor", "emailAddress": "fixture@example.test"},
        }
        if operation == "create_lead"
        else {"parent_id": "fixture", "text": "Fictional note"}
    )
    with pytest.raises(DomainValidationError):
        await runtime.gateway.invoke(context, tool_name, payload)
    result = await runtime.gateway.invoke(context, tool_name, payload)
    field = "external_id" if operation == "create_lead" else "note_id"
    assert result.status == "executed" and result.data[field] == "fictional-valid-123"
    replay = await runtime.gateway.invoke(context, tool_name, payload)
    assert replay.status == "replayed" and replay.data == result.data
    assert provider.await_count == 2


@pytest.mark.parametrize("identifier", ["fictional-record-123", "123", "x" * 128])
async def test_http_creation_preserves_valid_literal_identities(identifier):
    client = HttpEspoCRMClient(
        EspoCRMConfig(
            base_url="https://crm.example.test", api_key=SecretStr(secrets.token_hex(16))
        ),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"id": identifier})),
    )
    try:
        assert (
            await client.create_lead({"lastName": "Fictional"}, idempotency_key="fixture")
            == identifier
        )
        assert (
            await client.add_note(parent_type="Lead", parent_id="fixture", text="Note")
            == identifier
        )
    finally:
        await client.aclose()
