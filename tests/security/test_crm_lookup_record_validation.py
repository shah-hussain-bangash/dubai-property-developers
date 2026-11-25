"""Malformed provider lookup results cannot select a CRM update target."""

from unittest.mock import AsyncMock

import pytest

from core.policies.actions import ApprovalPolicy
from schemas.agents.models import AgentRunStatus
from tests.factories import normalized_lead

BAD_MATCHES = [
    None,
    {},
    "fictional-malformed-response",
    [None],
    ["fictional-malformed-record"],
    [{}],
    [{"id": None}],
    [{"id": 123}],
    [{"id": True}],
]


@pytest.mark.parametrize("matches", BAD_MATCHES)
@pytest.mark.parametrize("require_approval", [False, True])
async def test_invalid_lookup_response_blocks_writes_and_approvals(
    runtime, ctx, monkeypatch, matches, require_approval
):
    client = runtime.integrations.crm
    monkeypatch.setattr(client, "find_leads", AsyncMock(return_value=matches))
    methods = {}
    for name in ("create_lead", "update_lead", "add_note"):
        methods[name] = AsyncMock(return_value=None)
        monkeypatch.setattr(client, name, methods[name])
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=require_approval)
    result = await runtime.agents.get("crm").run(
        {"lead": normalized_lead().model_dump(mode="json")}, ctx
    )
    assert result.status == AgentRunStatus.FAILED
    assert result.error.code == "validation_error"
    assert await runtime.approvals.list_pending(ctx.tenant_id) == []
    assert client.leads == {}
    for method in methods.values():
        method.assert_not_awaited()


@pytest.mark.parametrize("external_id", ["fictional-record-123", "123"])
async def test_valid_string_identity_still_selects_the_existing_record(runtime, ctx, external_id):
    lead = normalized_lead()
    client = runtime.integrations.crm
    client.leads[external_id] = {
        "id": external_id,
        "lastName": "Original fictional visitor",
        "emailAddress": lead.email,
    }
    result = await runtime.agents.get("crm").run({"lead": lead.model_dump(mode="json")}, ctx)
    assert result.status == AgentRunStatus.SUCCEEDED
    assert result.output.external_id == external_id
    assert result.output.created is False
    assert client.leads[external_id]["id"] == external_id
    assert client.leads[external_id]["lastName"] != "Original fictional visitor"
    assert len(client.leads) == 1
