from __future__ import annotations

from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.crm.mapping import to_espocrm_lead
from agents.crm.schemas import CRMUpsertInput, CRMUpsertResult
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from tools.base import ToolResultStatus


class CRMAgent(BaseAgent[CRMUpsertInput, CRMUpsertResult]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="crm",
        name="CRM Agent",
        description="Persists leads locally and synchronizes them to EspoCRM (mock by default).",
        responsibilities=[
            "Create and update CRM leads",
            "Retrieve customer information",
            "Update activity histories",
            "Support CRM synchronization",
        ],
        implementation_status=ImplementationStatus.FUNCTIONAL,
        allowed_tools=frozenset(
            {"crm.find_leads", "crm.create_lead", "crm.update_lead", "crm.add_note", "leads.save"}
        ),
        status_notes="Functional against the mock CRM; EspoCRM HTTP adapter untested live. "
        "Opportunity management pending.",
    )
    input_model = CRMUpsertInput
    output_model = CRMUpsertResult

    async def execute(self, data: CRMUpsertInput, ctx: ExecutionContext) -> CRMUpsertResult:
        lead = data.lead
        await self.use_tool(ctx, "leads.save", {"lead": lead.model_dump(mode="json")})

        found = await self.use_tool(
            ctx, "crm.find_leads", {"email": lead.email, "phone": lead.phone_e164}
        )
        crm_data = to_espocrm_lead(lead, data.score)
        existing = found.data.get("leads", [])
        if existing:
            external_id = str(existing[0]["id"])
            write = await self.use_tool(
                ctx, "crm.update_lead", {"external_id": external_id, "data": crm_data},
                reason="Update existing CRM lead with new enquiry",
            )
            created = False
        else:
            write = await self.use_tool(
                ctx, "crm.create_lead", {"local_lead_id": lead.lead_id, "data": crm_data},
                reason="Create CRM lead for new enquiry",
            )
            external_id = write.data.get("external_id")
            created = write.status != ToolResultStatus.PENDING_APPROVAL

        note_id = None
        if external_id and write.status != ToolResultStatus.PENDING_APPROVAL and data.score:
            factors = "; ".join(f"{f.name} +{f.points}: {f.reason}" for f in data.score.factors)
            routing = f" Routed to {data.routing.queue} ({data.routing.priority})." if data.routing else ""
            note = await self.use_tool(
                ctx,
                "crm.add_note",
                {
                    "parent_type": "Lead",
                    "parent_id": external_id,
                    "text": f"AI qualification {data.score.score}/100 ({data.score.category.value}). "
                    f"Factors: {factors}.{routing}",
                },
            )
            note_id = note.data.get("note_id")

        return CRMUpsertResult(
            lead_id=lead.lead_id,
            external_id=external_id,
            created=created,
            status=write.status.value,
            approval_id=write.approval_id,
            note_id=note_id,
        )

    def outcome_status(self, output: CRMUpsertResult) -> AgentRunStatus:
        if output.status == ToolResultStatus.PENDING_APPROVAL:
            return AgentRunStatus.PENDING_APPROVAL
        return AgentRunStatus.SUCCEEDED
