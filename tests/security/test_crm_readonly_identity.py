"""Lead field dictionaries cannot overwrite the CRM's authoritative record ID."""

import secrets
from copy import deepcopy

import httpx
import pytest
from pydantic import SecretStr

from core.exceptions.errors import DomainValidationError
from core.policies.actions import ApprovalPolicy
from core.policies.approvals import ApprovalRequest
from integrations.espocrm.client import EspoCRMConfig, HttpEspoCRMClient, MockEspoCRMClient
from tools.base import ToolCallContext


def context(manager):
    return ToolCallContext(
        manager,
        manager.tenant_id,
        "fictional-crm-identity",
        "crm",
        frozenset({"crm.create_lead", "crm.update_lead"}),
    )


@pytest.mark.parametrize("operation", ["create_lead", "update_lead"])
@pytest.mark.parametrize("require_approval", [False, True])
@pytest.mark.parametrize("injected_id", ["fictional-other-record", None, "mock-lead-00001"])
async def test_identity_field_is_rejected_before_crm_approval_or_write(
    runtime, manager, operation, require_approval, injected_id
):
    client = runtime.integrations.crm
    external_id = await client.create_lead(
        {"lastName": "Original fictional visitor"}, idempotency_key="fictional-existing"
    )
    before = deepcopy(client.leads)
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=require_approval)
    payload = {
        "local_lead_id": "fictional-source",
        "external_id": external_id,
        "data": {"id": injected_id, "lastName": "Changed", "emailAddress": "fixture@example.test"},
    }
    with pytest.raises(DomainValidationError, match="ID is read-only"):
        await runtime.gateway.invoke(context(manager), f"crm.{operation}", payload)
    assert client.leads == before
    assert await runtime.approvals.list_pending(manager.tenant_id) == []


@pytest.mark.parametrize("adapter", ["mock", "http"])
@pytest.mark.parametrize("operation", ["create_lead", "update_lead"])
async def test_adapters_also_reject_identity_fields(adapter, operation):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "fictional-provider-record"})

    client = (
        HttpEspoCRMClient(
            EspoCRMConfig(
                base_url="https://crm.example.test", api_key=SecretStr(secrets.token_hex(16))
            ),
            transport=httpx.MockTransport(handler),
        )
        if adapter == "http"
        else MockEspoCRMClient()
    )
    try:
        with pytest.raises(DomainValidationError, match="ID is read-only"):
            if operation == "create_lead":
                await client.create_lead({"id": "fictional-forged"}, idempotency_key="fictional")
            else:
                if adapter == "mock":
                    await client.create_lead({"lastName": "Original"}, idempotency_key="existing")
                await client.update_lead("mock-lead-00001", {"id": "fictional-forged"})
        assert requests == []
        if adapter == "mock":
            assert all(key == lead["id"] for key, lead in client.leads.items())
    finally:
        if adapter == "http":
            await client.aclose()


@pytest.mark.parametrize("data", [None, [], "fictional"])
async def test_update_requires_object_fields_before_approval(runtime, manager, data):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    with pytest.raises(DomainValidationError, match="data must be an object"):
        await runtime.gateway.invoke(
            context(manager), "crm.update_lead", {"external_id": "fictional-record", "data": data}
        )
    assert await runtime.approvals.list_pending(manager.tenant_id) == []


async def test_normal_approved_update_retains_record_identity(runtime, manager):
    client = runtime.integrations.crm
    external_id = await client.create_lead(
        {"lastName": "Original fictional visitor"}, idempotency_key="fictional-existing"
    )
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    queued = await runtime.gateway.invoke(
        context(manager),
        "crm.update_lead",
        {"external_id": external_id, "data": {"lastName": "Reviewed fictional visitor"}},
    )
    assert queued.status == "pending_approval"
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    await runtime.gateway.execute_approved(queued.approval_id, manager)
    saved = await client.get_lead(external_id)
    assert saved["id"] == external_id
    assert saved["lastName"] == "Reviewed fictional visitor"


async def test_legacy_approved_identity_change_is_rejected(runtime, manager):
    client = runtime.integrations.crm
    external_id = await client.create_lead(
        {"lastName": "Original fictional visitor"}, idempotency_key="fictional-existing"
    )
    queued = await runtime.approvals.create(
        ApprovalRequest(
            tenant_id=manager.tenant_id,
            tool_name="crm.update_lead",
            action_category="crm_write",
            requested_by=manager.subject,
            requested_by_agent="crm",
            reason="Fictional legacy identity change",
            payload={"external_id": external_id, "data": {"id": "fictional-forged"}},
            idempotency_key="fictional-legacy-identity",
        )
    )
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    with pytest.raises(DomainValidationError, match="ID is read-only"):
        await runtime.gateway.execute_approved(queued.approval_id, manager)
    assert (await client.get_lead(external_id))["id"] == external_id
