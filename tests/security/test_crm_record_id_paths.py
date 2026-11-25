"""CRM record identifiers cannot change the route or create unsafe approvals."""

import secrets
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from core.exceptions.errors import DomainValidationError
from core.policies.actions import ApprovalPolicy
from core.policies.approvals import ApprovalRequest
from integrations.espocrm.client import EspoCRMConfig, HttpEspoCRMClient, MockEspoCRMClient
from tools.base import ToolCallContext

UNSAFE_IDS = [
    "",
    ".",
    "..",
    "../User/fictional",
    "fictional/../../User",
    "fictional\\other",
    "%2e%2e%2fUser",
    "%252e%252e%252fUser",
    "fictional?select=password",
    "fictional#fragment",
    " fictional ",
    "fictional\n",
    "fictional\x00",
    "fictional\uff0fother",
    "a" * 129,
    None,
    123,
    ["fictional"],
]


@pytest.mark.parametrize("external_id", UNSAFE_IDS)
@pytest.mark.parametrize("operation", ["get_lead", "update_lead"])
async def test_http_rejects_unsafe_id_before_transport(external_id, operation):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "fictional"})

    client = HttpEspoCRMClient(
        EspoCRMConfig(
            base_url="https://crm.example.test", api_key=SecretStr(secrets.token_hex(16))
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        args = (external_id, {}) if operation == "update_lead" else (external_id,)
        with pytest.raises(DomainValidationError, match="CRM record ID"):
            await getattr(client, operation)(*args)
        assert requests == []
    finally:
        await client.aclose()


@pytest.mark.parametrize("external_id", ["1", "mock-lead-00001", "AbC_123", "a" * 128])
async def test_valid_ids_keep_get_and_update_on_the_lead_route(external_id):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": external_id})

    client = HttpEspoCRMClient(
        EspoCRMConfig(
            base_url="https://crm.example.test", api_key=SecretStr(secrets.token_hex(16))
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await client.get_lead(external_id) == {"id": external_id}
        await client.update_lead(external_id, {"lastName": "Fictional visitor"})
        assert [r.method for r in requests] == ["GET", "PUT"]
        for request in requests:
            assert request.url.path == f"/api/v1/Lead/{external_id}"
            assert request.url.query == b""
            assert request.url.fragment == ""
    finally:
        await client.aclose()


@pytest.mark.parametrize("operation", ["get_lead", "update_lead"])
async def test_mock_rejects_the_same_path_attack(operation):
    client = MockEspoCRMClient()
    attack = "../User/fictional"
    client.leads[attack] = {"lastName": "Original fictional visitor"}
    args = (attack, {"lastName": "Changed"}) if operation == "update_lead" else (attack,)
    with pytest.raises(DomainValidationError, match="CRM record ID"):
        await getattr(client, operation)(*args)
    assert client.leads[attack] == {"lastName": "Original fictional visitor"}


@pytest.mark.parametrize("external_id", UNSAFE_IDS)
async def test_invalid_update_cannot_create_approval(runtime, manager, monkeypatch, external_id):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    update = AsyncMock(return_value=None)
    monkeypatch.setattr(runtime.integrations.crm, "update_lead", update)
    ctx = ToolCallContext(
        manager, manager.tenant_id, "fictional-crm-path", "crm", frozenset({"crm.update_lead"})
    )
    with pytest.raises(DomainValidationError, match="CRM record ID"):
        await runtime.gateway.invoke(
            ctx, "crm.update_lead", {"external_id": external_id, "data": {"lastName": "Fictional"}}
        )
    update.assert_not_awaited()
    assert await runtime.approvals.list_pending(manager.tenant_id) == []


async def test_legacy_approved_path_attack_is_rejected(runtime, manager, monkeypatch):
    update = AsyncMock(return_value=None)
    monkeypatch.setattr(runtime.integrations.crm, "update_lead", update)
    queued = await runtime.approvals.create(
        ApprovalRequest(
            tenant_id=manager.tenant_id,
            tool_name="crm.update_lead",
            action_category="crm_write",
            requested_by=manager.subject,
            requested_by_agent="crm",
            reason="Fictional approval predating ID validation",
            payload={"external_id": "../User/fictional", "data": {"lastName": "Fictional"}},
            idempotency_key="fictional-legacy-path",
        )
    )
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    with pytest.raises(DomainValidationError, match="CRM record ID"):
        await runtime.gateway.execute_approved(queued.approval_id, manager)
    update.assert_not_awaited()


async def test_valid_update_still_completes_after_approval(runtime, manager):
    client = runtime.integrations.crm
    external_id = await client.create_lead(
        {"lastName": "Fictional visitor"}, idempotency_key="fictional-path-positive"
    )
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    ctx = ToolCallContext(
        manager, manager.tenant_id, "fictional-crm-path", "crm", frozenset({"crm.update_lead"})
    )
    queued = await runtime.gateway.invoke(
        ctx, "crm.update_lead", {"external_id": external_id, "data": {"lastName": "Reviewed"}}
    )
    assert queued.status == "pending_approval"
    assert (await client.get_lead(external_id))["lastName"] == "Fictional visitor"
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    result = await runtime.gateway.execute_approved(queued.approval_id, manager)
    assert result.data == {"external_id": external_id, "updated": True}
    assert (await client.get_lead(external_id))["lastName"] == "Reviewed"
