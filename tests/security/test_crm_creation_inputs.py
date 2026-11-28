"""CRM creation requires a source enquiry identity before approval or delivery."""

import pytest

from core.exceptions.errors import DomainValidationError
from core.policies.actions import ApprovalPolicy
from core.policies.approvals import ApprovalRequest
from tools.base import ToolCallContext

BAD_IDENTITIES = [
    {},
    {"local_lead_id": None},
    {"local_lead_id": ""},
    {"local_lead_id": "   "},
    {"local_lead_id": 123},
    {"local_lead_id": False},
    {"local_lead_id": []},
    {"local_lead_id": {}},
]


def context(manager):
    return ToolCallContext(
        manager,
        manager.tenant_id,
        "fictional-crm-creation",
        "crm",
        frozenset({"crm.create_lead"}),
    )


def data():
    return {"lastName": "Fictional visitor", "emailAddress": "fixture@example.test"}


@pytest.mark.parametrize("identity", BAD_IDENTITIES)
@pytest.mark.parametrize("require_approval", [False, True])
async def test_invalid_source_identity_cannot_create_record_or_approval(
    runtime, manager, identity, require_approval
):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=require_approval)
    with pytest.raises(DomainValidationError, match="source enquiry ID"):
        await runtime.gateway.invoke(
            context(manager), "crm.create_lead", {**identity, "data": data()}
        )
    assert runtime.integrations.crm.leads == {}
    assert await runtime.approvals.list_pending(manager.tenant_id) == []


@pytest.mark.parametrize("invalid_data", [[], "fictional", 123])
async def test_non_object_lead_data_is_a_validation_error(runtime, manager, invalid_data):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    with pytest.raises(DomainValidationError, match="data must be an object"):
        await runtime.gateway.invoke(
            context(manager),
            "crm.create_lead",
            {"local_lead_id": "fictional-source", "data": invalid_data},
        )
    assert runtime.integrations.crm.leads == {}
    assert await runtime.approvals.list_pending(manager.tenant_id) == []


async def test_legacy_approved_request_without_source_identity_is_rejected(runtime, manager):
    queued = await runtime.approvals.create(
        ApprovalRequest(
            tenant_id=manager.tenant_id,
            tool_name="crm.create_lead",
            action_category="crm_write",
            requested_by=manager.subject,
            requested_by_agent="crm",
            reason="Fictional approval predating source ID validation",
            payload={"local_lead_id": None, "data": data()},
            idempotency_key="fictional-legacy-creation",
        )
    )
    await runtime.approvals.decide(queued.approval_id, approved=True, decided_by=manager.subject)
    with pytest.raises(DomainValidationError, match="source enquiry ID"):
        await runtime.gateway.execute_approved(queued.approval_id, manager)
    assert runtime.integrations.crm.leads == {}


async def test_valid_source_ids_keep_distinct_approved_records_and_replay(runtime, manager):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    created_ids = []
    for index in range(2):
        payload = {
            "local_lead_id": f"fictional-source-{index}",
            "data": {**data(), "lastName": f"Fictional visitor {index}"},
        }
        queued = await runtime.gateway.invoke(context(manager), "crm.create_lead", payload)
        assert queued.status == "pending_approval"
        await runtime.approvals.decide(
            queued.approval_id, approved=True, decided_by=manager.subject
        )
        created = await runtime.gateway.execute_approved(queued.approval_id, manager)
        replay = await runtime.gateway.invoke(context(manager), "crm.create_lead", payload)
        assert replay.status == "replayed"
        assert replay.data == created.data
        created_ids.append(created.data["external_id"])
    assert len(set(created_ids)) == 2
    assert len(runtime.integrations.crm.leads) == 2
