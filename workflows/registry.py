from __future__ import annotations

from typing import Any

from core.exceptions.errors import NotFoundError
from workflows.crm_sync_flow import CRM_SYNC
from workflows.customer_support_flow import KNOWLEDGE_SUPPORT
from workflows.engine.core import WorkflowDefinition, WorkflowDescriptor
from workflows.followup_flow import FOLLOWUP_AUTOMATION
from workflows.lead_flow import LEAD_PROCESSING
from workflows.property_flow import PROPERTY_RECOMMENDATION
from workflows.qualification_flow import LEAD_REQUALIFICATION
from workflows.sales_flow import SALES_CONVERSATION

# The six primary workflows (in specification order), then sub-flows.
WORKFLOWS: dict[str, WorkflowDefinition[Any]] = {
    wf.workflow_id: wf
    for wf in (
        LEAD_PROCESSING,
        PROPERTY_RECOMMENDATION,
        SALES_CONVERSATION,
        FOLLOWUP_AUTOMATION,
        CRM_SYNC,
        KNOWLEDGE_SUPPORT,
        LEAD_REQUALIFICATION,
    )
}


def get_workflow(workflow_id: str) -> WorkflowDefinition[Any]:
    try:
        return WORKFLOWS[workflow_id]
    except KeyError as exc:
        raise NotFoundError(f"workflow '{workflow_id}' not found") from exc


def workflow_descriptors() -> list[WorkflowDescriptor]:
    return [wf.descriptor() for wf in WORKFLOWS.values()]
