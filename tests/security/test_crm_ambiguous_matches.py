"""Conflicting CRM matches require review instead of selecting the first customer."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from core.policies.actions import ApprovalPolicy
from schemas.agents.models import AgentRunStatus
from tests.factories import normalized_lead


@pytest.mark.parametrize("require_approval", [False, True])
@pytest.mark.parametrize("reverse_order", [False, True])
async def test_email_and_phone_matching_different_records_blocks_crm_writes(
    runtime, ctx, monkeypatch, require_approval, reverse_order
):
    lead = normalized_lead()
    client = runtime.integrations.crm
    records = [
        {"lastName": "Fictional email owner", "emailAddress": lead.email},
        {"lastName": "Fictional phone owner", "phoneNumber": lead.phone_e164},
    ]
    for index, record in enumerate(reversed(records) if reverse_order else records):
        await client.create_lead(record, idempotency_key=f"fictional-{index}")
    before = deepcopy(client.leads)
    methods = {}
    for name in ("create_lead", "update_lead", "add_note"):
        methods[name] = AsyncMock(wraps=getattr(client, name))
        monkeypatch.setattr(client, name, methods[name])
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=require_approval)

    result = await runtime.agents.get("crm").run({"lead": lead.model_dump(mode="json")}, ctx)

    assert result.status == AgentRunStatus.FAILED
    assert result.error.code == "validation_error"
    assert "multiple CRM records" in result.error.message
    assert lead.email not in result.error.message
    assert lead.phone_e164 not in result.error.message
    assert client.leads == before
    assert await runtime.approvals.list_pending(ctx.tenant_id) == []
    for method in methods.values():
        method.assert_not_awaited()


async def test_duplicate_email_records_also_require_review(runtime, ctx):
    lead = normalized_lead(phone_e164=None)
    client = runtime.integrations.crm
    for index in range(2):
        await client.create_lead(
            {"lastName": f"Fictional visitor {index}", "emailAddress": lead.email},
            idempotency_key=f"fictional-{index}",
        )
    before = deepcopy(client.leads)
    result = await runtime.agents.get("crm").run({"lead": lead.model_dump(mode="json")}, ctx)
    assert result.status == AgentRunStatus.FAILED
    assert result.error.code == "validation_error"
    assert client.leads == before


@pytest.mark.parametrize("matched_field", ["email", "phone", "both"])
async def test_single_matching_record_keeps_normal_update(runtime, ctx, matched_field):
    lead = normalized_lead()
    client = runtime.integrations.crm
    record = {"lastName": "Fictional existing visitor"}
    if matched_field in {"email", "both"}:
        record["emailAddress"] = lead.email
    if matched_field in {"phone", "both"}:
        record["phoneNumber"] = lead.phone_e164
    external_id = await client.create_lead(record, idempotency_key="fictional-existing")
    result = await runtime.agents.get("crm").run({"lead": lead.model_dump(mode="json")}, ctx)
    assert result.status == AgentRunStatus.SUCCEEDED
    assert result.output.external_id == external_id
    assert result.output.created is False
    assert (await client.get_lead(external_id))["lastName"] != "Fictional existing visitor"
    assert len(client.leads) == 1
