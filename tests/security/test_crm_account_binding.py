"""One configured CRM account must not be used by a different organization."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from core.exceptions.errors import AuthorizationError
from core.policies.actions import ApprovalPolicy
from core.policies.approvals import ApprovalRequest
from core.resilience.idempotency import make_idempotency_key
from integrations.espocrm.client import MockEspoCRMClient
from tools.base import ToolCallContext
from tools.crm.tools import CRMAddNoteTool, CRMCreateLeadTool, CRMFindLeadsTool, CRMUpdateLeadTool

CASES = [
    ("crm.find_leads", {"email": "fixture@example.com"}, CRMFindLeadsTool),
    (
        "crm.create_lead",
        {
            "local_lead_id": "fictional-common-id",
            "data": {"lastName": "Fictional visitor", "emailAddress": "fixture@example.com"},
        },
        CRMCreateLeadTool,
    ),
    (
        "crm.update_lead",
        {
            "external_id": "fictional-owner-record",
            "data": {"lastName": "Changed by another organization"},
        },
        CRMUpdateLeadTool,
    ),
    (
        "crm.add_note",
        {"parent_id": "fictional-owner-record", "text": "Fictional note"},
        CRMAddNoteTool,
    ),
]


def context(manager, tenant=None):
    actor = manager if tenant is None else replace(manager, tenant_id=tenant)
    return ToolCallContext(
        actor,
        actor.tenant_id,
        "fictional-crm-account-binding",
        "crm",
        frozenset(name for name, _, _ in CASES),
    )


@pytest.mark.parametrize("name,payload,tool_class", CASES)
async def test_foreign_organization_cannot_touch_shared_crm(
    runtime, manager, monkeypatch, name, payload, tool_class
):
    client = runtime.integrations.crm
    methods = {}
    for method in ["find_leads", "create_lead", "update_lead", "add_note"]:
        methods[method] = AsyncMock(return_value=[] if method == "find_leads" else "fictional-id")
        monkeypatch.setattr(client, method, methods[method])
    with pytest.raises(AuthorizationError):
        await runtime.gateway.invoke(context(manager, "other-org"), name, payload)
    for method in methods.values():
        method.assert_not_awaited()


@pytest.mark.parametrize("name,payload,tool_class", CASES[1:])
async def test_human_approval_cannot_override_crm_account_ownership(
    runtime, manager, monkeypatch, name, payload, tool_class
):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    method_name = {
        "crm.create_lead": "create_lead",
        "crm.update_lead": "update_lead",
        "crm.add_note": "add_note",
    }[name]
    method = AsyncMock(return_value="fictional-id")
    monkeypatch.setattr(runtime.integrations.crm, method_name, method)
    foreign = context(manager, "other-org")
    # Simulate an approval persisted before account ownership was enforced.
    queued = await runtime.approvals.create(
        ApprovalRequest(
            tenant_id=foreign.tenant_id,
            tool_name=name,
            action_category="crm_write",
            requested_by=manager.subject,
            requested_by_agent="crm",
            reason="Legacy fictional fixture",
            payload=payload,
            idempotency_key="fictional-legacy-crm-action",
        )
    )
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    cached = AsyncMock(return_value={"external_id": "fictional-foreign-result"})
    monkeypatch.setattr(runtime.gateway.idempotency, "get", cached)
    with pytest.raises(AuthorizationError):
        await runtime.gateway.execute_approved(queued.approval_id, foreign.principal)
    method.assert_not_awaited()
    cached.assert_not_awaited()


@pytest.mark.parametrize("name,payload,tool_class", CASES)
async def test_bound_runtime_tools_require_trusted_context(runtime, name, payload, tool_class):
    with pytest.raises(AuthorizationError):
        await runtime.tools.get(name).execute(payload)


async def test_own_workspace_keeps_create_find_update_and_note(runtime, manager):
    own = context(manager)
    created = await runtime.gateway.invoke(own, CASES[1][0], CASES[1][1])
    external = created.data["external_id"]
    found = await runtime.gateway.invoke(own, CASES[0][0], CASES[0][1])
    assert found.data["leads"][0]["id"] == external
    await runtime.gateway.invoke(
        own,
        "crm.update_lead",
        {"external_id": external, "data": {"lastName": "Reviewed fictional visitor"}},
    )
    await runtime.gateway.invoke(
        own, "crm.add_note", {"parent_id": external, "text": "Reviewed fictional note"}
    )
    assert (await runtime.integrations.crm.get_lead(external))[
        "lastName"
    ] == "Reviewed fictional visitor"
    assert runtime.integrations.crm.notes[0]["parentId"] == external


@pytest.mark.parametrize("name,payload,tool_class", CASES)
async def test_contextual_unbound_client_fails_closed(manager, name, payload, tool_class):
    tool = tool_class(MockEspoCRMClient())
    with pytest.raises(AuthorizationError):
        await tool.execute_with_context(payload, context(manager))


async def test_legacy_standalone_mock_client_is_still_usable():
    client = MockEspoCRMClient()
    created = await CRMCreateLeadTool(client).execute(CASES[1][1])
    result = await CRMFindLeadsTool(client).execute(CASES[0][1])
    assert result["leads"][0]["id"] == created["external_id"]


@pytest.mark.parametrize("name,payload,tool_class", CASES[1:])
async def test_foreign_workspace_cannot_create_approval(
    runtime, manager, name, payload, tool_class
):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    foreign = context(manager, "other-org")
    with pytest.raises(AuthorizationError):
        await runtime.gateway.invoke(foreign, name, payload)
    assert await runtime.approvals.list_pending(foreign.tenant_id) == []
    assert runtime.audit.events[-1].outcome == "denied"


@pytest.mark.parametrize("name,payload,tool_class", CASES[1:])
async def test_old_cached_result_cannot_bypass_binding(runtime, manager, name, payload, tool_class):
    foreign = context(manager, "other-org")
    key = make_idempotency_key(name, payload, scope=foreign.tenant_id, agent_id="crm")
    await runtime.gateway.idempotency.put(key, {"external_id": "fictional-foreign-result"}, 60)
    with pytest.raises(AuthorizationError):
        await runtime.gateway.invoke(foreign, name, payload)


async def test_direct_context_cannot_spoof_account_owner(runtime, manager):
    forged = replace(context(manager, "other-org"), tenant_id=manager.tenant_id)
    with pytest.raises(AuthorizationError):
        await runtime.tools.get("crm.find_leads").execute_with_context(CASES[0][1], forged)


async def test_runtime_binds_the_configured_workspace(settings, manager):
    from workflows.runtime import build_runtime

    settings.default_tenant_id = "fictional-account-owner"
    runtime = build_runtime(settings)
    await runtime.initialize()
    try:
        result = await runtime.gateway.invoke(
            context(manager, settings.default_tenant_id), "crm.find_leads", CASES[0][1]
        )
        assert result.data["leads"] == []
        with pytest.raises(AuthorizationError):
            await runtime.gateway.invoke(context(manager), "crm.find_leads", CASES[0][1])
    finally:
        await runtime.shutdown()
