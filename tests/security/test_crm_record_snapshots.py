"""Read results and caller-owned inputs cannot mutate mock CRM records."""

import pytest

from core.policies.actions import ApprovalPolicy
from core.security.rbac import Permission, Principal, Role
from integrations.espocrm.client import MockEspoCRMClient
from tools.base import ToolCallContext


def fictional_record():
    return {
        "lastName": "Fictional visitor",
        "emailAddress": "fixture@example.test",
        "phoneNumber": "+971500000001",
        "custom": {"consent": {"email": False}, "tags": ["fictional"]},
    }


@pytest.mark.parametrize("lookup", ["email", "phone"])
async def test_find_returns_detached_records(lookup):
    client = MockEspoCRMClient()
    original = fictional_record()
    external_id = await client.create_lead(original, idempotency_key="fictional")
    matches = await client.find_leads(
        email=original["emailAddress"] if lookup == "email" else None,
        phone=original["phoneNumber"] if lookup == "phone" else None,
    )
    matches[0]["lastName"] = "Changed through read"
    matches[0]["custom"]["consent"]["email"] = True
    matches[0]["custom"]["tags"].append("changed")
    assert await client.get_lead(external_id) == {"id": external_id, **fictional_record()}


async def test_get_returns_detached_nested_values():
    client = MockEspoCRMClient()
    external_id = await client.create_lead(fictional_record(), idempotency_key="fictional")
    result = await client.get_lead(external_id)
    result["custom"]["consent"]["email"] = True
    result["custom"]["tags"].clear()
    assert await client.get_lead(external_id) == {"id": external_id, **fictional_record()}


async def test_create_snapshots_caller_owned_nested_values():
    client = MockEspoCRMClient()
    payload = fictional_record()
    external_id = await client.create_lead(payload, idempotency_key="fictional")
    payload["custom"]["consent"]["email"] = True
    payload["custom"]["tags"].clear()
    assert await client.get_lead(external_id) == {"id": external_id, **fictional_record()}


async def test_update_snapshots_caller_owned_nested_values():
    client = MockEspoCRMClient()
    external_id = await client.create_lead(fictional_record(), idempotency_key="fictional")
    payload = {"custom": {"consent": {"email": True}, "tags": ["reviewed"]}}
    await client.update_lead(external_id, payload)
    payload["custom"]["consent"]["email"] = False
    payload["custom"]["tags"].clear()
    saved = await client.get_lead(external_id)
    assert saved["custom"] == {"consent": {"email": True}, "tags": ["reviewed"]}
    assert saved["lastName"] == "Fictional visitor"


@pytest.mark.parametrize("lookup", ["get", "find"])
async def test_later_updates_do_not_change_existing_read_snapshots(lookup):
    client = MockEspoCRMClient()
    external_id = await client.create_lead(fictional_record(), idempotency_key="fictional")
    result = (
        await client.get_lead(external_id)
        if lookup == "get"
        else (await client.find_leads(email="fixture@example.test", phone=None))[0]
    )
    # Mutating an internal nested value models a later CRM-side edit.
    client.leads[external_id]["custom"]["tags"].append("later-edit")
    await client.update_lead(external_id, {"lastName": "Later visitor name"})
    assert result == {"id": external_id, **fictional_record()}


async def test_viewer_search_cannot_bypass_crm_write_approval(runtime, manager):
    client = runtime.integrations.crm
    external_id = await client.create_lead(fictional_record(), idempotency_key="fictional")
    viewer = Principal(
        subject="fictional-viewer", tenant_id=manager.tenant_id, roles=frozenset({Role.VIEWER})
    )
    assert not viewer.has(Permission.CRM_WRITE)
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    ctx = ToolCallContext(
        viewer,
        viewer.tenant_id,
        "fictional-crm-snapshot",
        "crm",
        frozenset({"crm.find_leads"}),
    )
    result = await runtime.gateway.invoke(ctx, "crm.find_leads", {"email": "fixture@example.test"})
    result.data["leads"][0]["lastName"] = "Unapproved change"
    result.data["leads"][0]["custom"]["consent"]["email"] = True
    assert await client.get_lead(external_id) == {"id": external_id, **fictional_record()}
    assert await runtime.approvals.list_pending(viewer.tenant_id) == []
