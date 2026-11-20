from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agents.base.context import ExecutionContext
from core.security.rbac import Principal, Role
from schemas.events.models import ExternalRecordEvent, SyncOperation
from tests.factories import TENANT, submission
from workflows.crm_sync_flow import CRM_SYNC, CRMSyncState, LocalRecordSnapshot, SyncDecision, resolve
from workflows.customer_support_flow import KNOWLEDGE_SUPPORT, SupportFlowState
from workflows.engine.core import WorkflowStatus
from workflows.followup_flow import FOLLOWUP_AUTOMATION, FollowUpFlowState
from workflows.lead_flow import LEAD_PROCESSING, LeadFlowState
from workflows.property_flow import PROPERTY_RECOMMENDATION, PropertyFlowState
from workflows.registry import WORKFLOWS, workflow_descriptors
from workflows.runtime import PlatformRuntime
from workflows.sales_flow import SALES_CONVERSATION, SalesFlowState


def test_all_six_primary_workflows_registered() -> None:
    required = {
        "lead_processing", "property_recommendation", "sales_conversation",
        "followup_automation", "crm_sync", "knowledge_support",
    }
    assert required <= set(WORKFLOWS)
    assert all(d.steps for d in workflow_descriptors())


async def test_lead_processing_end_to_end(runtime: PlatformRuntime, ctx: ExecutionContext) -> None:
    run, state = await runtime.runner.run(LEAD_PROCESSING, LeadFlowState(submission=submission()), ctx)
    assert run.status == WorkflowStatus.SUCCEEDED, run.error
    assert [s.name for s in run.steps] == [
        "validate_normalize_deduplicate", "duplicate_gate", "qualify", "route", "store_in_crm",
    ]
    assert state.lead and state.lead.phone_e164 == "+971500000001"
    assert state.qualification and state.routing and state.routing.queue == "sales-priority"
    assert state.crm and state.crm.created and state.crm.note_id
    crm_record = runtime.integrations.crm.leads[state.crm.external_id]  # type: ignore[attr-defined,index]
    assert crm_record["source"] == "Web Site"

    # Same person again -> stops at the duplicate gate, no second CRM record.
    run2, state2 = await runtime.runner.run(LEAD_PROCESSING, LeadFlowState(submission=submission()), ctx)
    assert run2.status == WorkflowStatus.SUCCEEDED and state2.is_duplicate
    assert run2.steps[-1].name == "duplicate_gate" and state2.crm is None
    assert len(runtime.integrations.crm.leads) == 1  # type: ignore[attr-defined]


async def test_lead_processing_fails_cleanly_on_bad_lead(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    run, _ = await runtime.runner.run(
        LEAD_PROCESSING, LeadFlowState(submission=submission(email=None, phone="12")), ctx
    )
    assert run.status == WorkflowStatus.FAILED
    assert run.error and run.error["code"] == "workflow_error"


async def test_property_recommendation_flow(runtime: PlatformRuntime, ctx: ExecutionContext) -> None:
    run, state = await runtime.runner.run(
        PROPERTY_RECOMMENDATION, PropertyFlowState(criteria={"budget_max_aed": "7000000"}), ctx  # type: ignore[arg-type]
    )
    assert run.status == WorkflowStatus.SUCCEEDED
    assert state.output and state.output.recommendations


async def test_sales_flow_whatsapp_reply_awaits_approval(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    state = SalesFlowState.model_validate(
        {
            "message": {
                "conversation_id": "wa-flow",
                "channel": "whatsapp",
                "direction": "inbound",
                "sender": "customer",
                "text": "What is the payment plan for Demo Creek Heights?",
            },
            "customer_first_name": "Demo",
            "customer_e164": "+971500000001",
            "consent_whatsapp": True,
        }
    )
    run, final = await runtime.runner.run(SALES_CONVERSATION, state, ctx)
    assert run.status == WorkflowStatus.PENDING_APPROVAL
    assert final.whatsapp and final.whatsapp.approval_id
    assert runtime.integrations.whatsapp.outbox == []  # type: ignore[attr-defined]


async def test_sales_flow_escalates_complaint(runtime: PlatformRuntime, ctx: ExecutionContext) -> None:
    state = SalesFlowState.model_validate(
        {
            "message": {
                "conversation_id": "web-1",
                "channel": "web_chat",
                "direction": "inbound",
                "sender": "customer",
                "text": "This is a complaint about my booking",
            }
        }
    )
    run, _ = await runtime.runner.run(SALES_CONVERSATION, state, ctx)
    assert run.status == WorkflowStatus.ESCALATED


async def test_followup_flow_then_human_approval_sends(
    runtime: PlatformRuntime, system_ctx: ExecutionContext
) -> None:
    now = datetime.now(UTC)
    request = {
        "tasks": [
            {
                "task_id": "t1",
                "lead_id": "l1",
                "contact_first_name": "Demo",
                "channel": "email",
                "email": "demo.lead.one@example.com",
                "due_at": (now - timedelta(hours=2)).isoformat(),
            }
        ]
    }
    run, state = await runtime.runner.run(
        FOLLOWUP_AUTOMATION, FollowUpFlowState(request=request), system_ctx  # type: ignore[arg-type]
    )
    assert run.status == WorkflowStatus.PENDING_APPROVAL
    assert state.plan
    approval_id = state.plan.actions[0].approval_id
    assert approval_id and runtime.email_sender.outbox == []

    approver = Principal(subject="mgr", tenant_id=TENANT, roles=frozenset({Role.SALES_MANAGER}))
    await runtime.approvals.decide(approval_id, approved=True, decided_by="mgr")
    await runtime.gateway.execute_approved(approval_id, approver)
    assert len(runtime.email_sender.outbox) == 1
    assert any(e.outcome == "executed" for e in runtime.audit.events)


def test_crm_conflict_resolution_rules() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    event = ExternalRecordEvent(
        source_system="espocrm", entity_type="lead", external_id="e1",
        operation=SyncOperation.UPDATE, occurred_at=t0 + timedelta(hours=2), data={"status": "In Process"},
    )
    clean = LocalRecordSnapshot(local_id="l1", updated_at=t0, last_synced_at=t0)
    dirty_newer = LocalRecordSnapshot(local_id="l1", updated_at=t0 + timedelta(hours=3), last_synced_at=t0)
    assert resolve(event, None) == SyncDecision.CREATE_LOCAL
    assert resolve(event, clean) == SyncDecision.APPLY_EXTERNAL
    assert resolve(event, dirty_newer) == SyncDecision.CONFLICT
    assert resolve(event.model_copy(update={"operation": SyncOperation.DELETE}), clean) == SyncDecision.CONFLICT


async def test_crm_sync_flow_applies_and_audits(runtime: PlatformRuntime, system_ctx: ExecutionContext) -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    state = CRMSyncState(
        event=ExternalRecordEvent(
            source_system="espocrm", entity_type="lead", external_id="e1",
            operation=SyncOperation.UPDATE, occurred_at=t0 + timedelta(hours=1),
            data={"status": "In Process", "firstName": "Demo"},
        ),
        local=LocalRecordSnapshot(local_id="l1", updated_at=t0, last_synced_at=t0, data={"firstName": "Demo"}),
    )
    run, final = await runtime.runner.run(CRM_SYNC, state, system_ctx)
    assert run.status == WorkflowStatus.SUCCEEDED
    assert final.changes == {"status": "In Process"}
    events = runtime.deps.events.published  # type: ignore[attr-defined]
    assert events[-1].event_type == "crm.sync.processed"


async def test_knowledge_support_answer_and_handoff(runtime: PlatformRuntime, ctx: ExecutionContext) -> None:
    run, state = await runtime.runner.run(
        KNOWLEDGE_SUPPORT, SupportFlowState(question="Demo Creek Heights payment plan"), ctx
    )
    assert run.status == WorkflowStatus.PENDING_APPROVAL  # customer answer awaits approval
    assert state.answer and state.answer.citations

    run2, _ = await runtime.runner.run(
        KNOWLEDGE_SUPPORT, SupportFlowState(question="zzqx unrelated vocabulary"), ctx
    )
    assert run2.status == WorkflowStatus.ESCALATED
