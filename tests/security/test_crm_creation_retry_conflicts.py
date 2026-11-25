"""A source enquiry's creation retry cannot acknowledge different CRM data."""

from copy import deepcopy

import pytest

from core.exceptions.errors import ConflictError, DomainValidationError
from core.policies.actions import ApprovalPolicy
from integrations.espocrm.client import MockEspoCRMClient
from schemas.agents.models import AgentRunStatus
from tests.factories import normalized_lead
from tools.base import ToolCallContext


def original_data():
    return {
        "lastName": "Original fictional visitor",
        "emailAddress": "fixture@example.test",
        "custom": {"consent": True, "tags": ["fictional"]},
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"lastName": "Changed fictional visitor"},
        {"emailAddress": "other@example.test"},
        {"custom": {"consent": True, "tags": ["changed"]}},
        {"custom": {"consent": 1, "tags": ["fictional"]}},
    ],
)
async def test_changed_creation_data_cannot_reuse_the_same_retry_key(patch):
    client = MockEspoCRMClient()
    external_id = await client.create_lead(original_data(), idempotency_key="fictional-source")
    before = deepcopy(client.leads)
    with pytest.raises(ConflictError, match="different creation data") as rejected:
        await client.create_lead({**original_data(), **patch}, idempotency_key="fictional-source")
    assert rejected.value.details == {}
    assert "fixture@example.test" not in str(rejected.value)
    assert client.leads == before
    assert (
        await client.create_lead(original_data(), idempotency_key="fictional-source") == external_id
    )


async def test_equivalent_reordered_json_is_a_valid_retry():
    client = MockEspoCRMClient()
    payload = original_data()
    external_id = await client.create_lead(payload, idempotency_key="fictional-source")
    reordered = dict(reversed(list(payload.items())))
    reordered["custom"] = {"tags": ["fictional"], "consent": True}
    assert await client.create_lead(reordered, idempotency_key="fictional-source") == external_id
    assert len(client.leads) == 1


async def test_later_updates_do_not_rewrite_the_original_creation_receipt():
    client = MockEspoCRMClient()
    payload = original_data()
    external_id = await client.create_lead(payload, idempotency_key="fictional-source")
    await client.update_lead(external_id, {"lastName": "Later approved update"})
    payload["custom"]["tags"].append("caller edit")
    assert (
        await client.create_lead(original_data(), idempotency_key="fictional-source") == external_id
    )
    assert (await client.get_lead(external_id))["lastName"] == "Later approved update"


async def test_second_human_approval_cannot_acknowledge_a_conflicting_create(runtime, manager):
    runtime.gateway.approval_policy = ApprovalPolicy(crm_writes=True)
    call_ctx = ToolCallContext(
        manager,
        manager.tenant_id,
        "fictional-retry-conflict",
        "crm",
        frozenset({"crm.create_lead"}),
    )
    payload = {"local_lead_id": "fictional-source", "data": original_data()}
    first = await runtime.gateway.invoke(call_ctx, "crm.create_lead", payload)
    await runtime.approvals.decide(first.approval_id, approved=True, decided_by=manager.subject)
    await runtime.gateway.execute_approved(first.approval_id, manager)
    before = deepcopy(runtime.integrations.crm.leads)
    changed = {**payload, "data": {**original_data(), "emailAddress": "other@example.test"}}
    second = await runtime.gateway.invoke(call_ctx, "crm.create_lead", changed)
    assert second.approval_id != first.approval_id
    await runtime.approvals.decide(second.approval_id, approved=True, decided_by=manager.subject)
    with pytest.raises(ConflictError):
        await runtime.gateway.execute_approved(second.approval_id, manager)
    assert runtime.integrations.crm.leads == before


async def test_agent_cannot_report_old_creation_as_success_for_changed_contacts(runtime, ctx):
    agent = runtime.agents.get("crm")
    lead = normalized_lead()
    first = await agent.run({"lead": lead.model_dump(mode="json")}, ctx)
    assert first.status == AgentRunStatus.SUCCEEDED
    before = deepcopy(runtime.integrations.crm.leads)
    changed = lead.model_copy(update={"email": "other@example.test", "phone_e164": "+971500000002"})
    second = await agent.run({"lead": changed.model_dump(mode="json")}, ctx)
    assert second.status == AgentRunStatus.FAILED
    assert second.error.code == "conflict"
    assert runtime.integrations.crm.leads == before


@pytest.mark.parametrize("value", [{"not-json"}, float("nan")])
async def test_unserializable_creation_does_not_reserve_a_retry_key(value):
    client = MockEspoCRMClient()
    with pytest.raises(DomainValidationError, match="valid JSON"):
        await client.create_lead(
            {**original_data(), "custom": value}, idempotency_key="fictional-source"
        )
    assert client.leads == {}
    external_id = await client.create_lead(original_data(), idempotency_key="fictional-source")
    assert (await client.get_lead(external_id))["emailAddress"] == "fixture@example.test"
