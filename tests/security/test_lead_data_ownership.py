"""Lead payloads and mutable snapshots cannot change organization ownership."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from core.exceptions.errors import AuthorizationError
from tests.factories import normalized_lead
from tools.base import ToolCallContext
from tools.search.lead_store import InMemoryLeadStore


def context(manager):
    return ToolCallContext(
        manager,
        manager.tenant_id,
        "fictional-lead-ownership",
        "crm",
        frozenset({"leads.save", "search.lead_duplicates"}),
    )


@pytest.mark.parametrize("action", ["save", "search"])
async def test_foreign_payload_is_denied_before_store_access(runtime, manager, monkeypatch, action):
    foreign = normalized_lead(tenant_id="other-org", dedupe_keys=["fictional:private"])
    save = AsyncMock()
    search = AsyncMock(return_value=[foreign])
    monkeypatch.setattr(runtime.lead_store, "save", save)
    monkeypatch.setattr(runtime.lead_store, "find_by_dedupe_keys", search)
    tool = "leads.save" if action == "save" else "search.lead_duplicates"
    payload = (
        {"lead": foreign.model_dump(mode="json")}
        if action == "save"
        else {"tenant_id": foreign.tenant_id, "dedupe_keys": foreign.dedupe_keys}
    )
    with pytest.raises(AuthorizationError):
        await runtime.gateway.invoke(context(manager), tool, payload)
    save.assert_not_awaited()
    search.assert_not_awaited()


@pytest.mark.parametrize("action", ["save", "search"])
async def test_direct_tool_calls_require_trusted_identity(runtime, manager, action):
    lead = normalized_lead()
    tool = "leads.save" if action == "save" else "search.lead_duplicates"
    payload = (
        {"lead": lead.model_dump(mode="json")}
        if action == "save"
        else {"tenant_id": lead.tenant_id, "dedupe_keys": lead.dedupe_keys}
    )
    with pytest.raises(AuthorizationError):
        await runtime.tools.get(tool).execute(payload)


@pytest.mark.parametrize("action", ["save", "search"])
async def test_contextual_tool_checks_principal_organization(runtime, manager, action):
    lead = normalized_lead()
    forged = replace(context(manager), principal=replace(manager, tenant_id="other-org"))
    tool = "leads.save" if action == "save" else "search.lead_duplicates"
    payload = (
        {"lead": lead.model_dump(mode="json")}
        if action == "save"
        else {"tenant_id": lead.tenant_id, "dedupe_keys": lead.dedupe_keys}
    )
    with pytest.raises(AuthorizationError):
        await runtime.tools.get(tool).execute_with_context(payload, forged)


async def test_reused_id_cannot_replace_foreign_record(runtime, manager):
    foreign = normalized_lead(tenant_id="other-org", dedupe_keys=["fictional:private"])
    await runtime.lead_store.save(foreign)
    own = normalized_lead(lead_id=foreign.lead_id, full_name="Fictional replacement")
    with pytest.raises(AuthorizationError):
        await runtime.gateway.invoke(
            context(manager), "leads.save", {"lead": own.model_dump(mode="json")}
        )
    assert await runtime.lead_store.list(manager.tenant_id) == []
    assert await runtime.lead_store.list(foreign.tenant_id) == [foreign]


async def test_memory_save_owns_a_deep_snapshot():
    store = InMemoryLeadStore()
    lead = normalized_lead(dedupe_keys=["fictional:original"])
    expected = lead.model_copy(deep=True)
    await store.save(lead)
    lead.tenant_id = "other-org"
    lead.dedupe_keys.append("fictional:changed")
    lead.consent_whatsapp = False
    assert await store.list(expected.tenant_id) == [expected]
    assert await store.list("other-org") == []


@pytest.mark.parametrize("method", ["list", "find"])
async def test_memory_reads_are_detached_snapshots(method):
    store = InMemoryLeadStore()
    lead = normalized_lead(dedupe_keys=["fictional:original"])
    await store.save(lead)
    result = (
        await store.list(lead.tenant_id)
        if method == "list"
        else await store.find_by_dedupe_keys(lead.tenant_id, lead.dedupe_keys)
    )
    result[0].tenant_id = "other-org"
    result[0].dedupe_keys.clear()
    result[0].consent_whatsapp = False
    assert await store.find_by_dedupe_keys(lead.tenant_id, lead.dedupe_keys) == [lead]
    assert await store.list("other-org") == []


async def test_each_organization_keeps_own_save_search_and_update(runtime, manager):
    for index, tenant in enumerate([manager.tenant_id, "other-org"]):
        actor = replace(manager, tenant_id=tenant)
        ctx = context(actor)
        lead = normalized_lead(
            tenant_id=tenant,
            lead_id=f"fictional-lead-{index}",
            dedupe_keys=["fictional:shared-contact"],
        )
        await runtime.gateway.invoke(ctx, "leads.save", {"lead": lead.model_dump(mode="json")})
        lead.full_name = f"Reviewed fictional visitor {index}"
        await runtime.gateway.invoke(ctx, "leads.save", {"lead": lead.model_dump(mode="json")})
        found = await runtime.gateway.invoke(
            ctx, "search.lead_duplicates", {"tenant_id": tenant, "dedupe_keys": lead.dedupe_keys}
        )
        assert len(found.data["matches"]) == 1
        assert found.data["matches"][0]["full_name"] == lead.full_name
        assert found.data["matches"][0]["tenant_id"] == tenant


async def test_crm_agent_rejects_foreign_lead_before_local_or_external_write(
    runtime, ctx, monkeypatch
):
    external = AsyncMock()
    monkeypatch.setattr(runtime.integrations.crm, "find_leads", external)
    result = await runtime.agents.get("crm").run(
        {"lead": normalized_lead(tenant_id="other-org").model_dump(mode="json")}, ctx
    )
    assert result.status == "failed"
    assert result.error.code == "forbidden"
    assert await runtime.lead_store.list("other-org") == []
    assert await runtime.lead_store.list(ctx.tenant_id) == []
    external.assert_not_awaited()
