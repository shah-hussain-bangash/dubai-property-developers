from __future__ import annotations

import uuid
from typing import ClassVar

from agents.base.agent import AgentSpec, BaseAgent
from agents.base.context import ExecutionContext
from agents.lead_intake.normalization import (
    dedupe_keys,
    normalize_email,
    normalize_location,
    normalize_phone,
)
from agents.lead_intake.schemas import LeadIntakeResult
from core.exceptions.errors import DomainValidationError
from schemas.agents.models import ImplementationStatus
from schemas.leads.models import LeadStatus, LeadSubmission, NormalizedLead


class LeadIntakeAgent(BaseAgent[LeadSubmission, LeadIntakeResult]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="lead_intake",
        name="Lead Intake Agent",
        description="Validates, normalizes and de-duplicates inbound leads.",
        responsibilities=[
            "Receive website and portal leads",
            "Validate required information",
            "Normalize phone numbers to E.164",
            "Detect duplicate leads",
            "Prepare structured lead records",
        ],
        implementation_status=ImplementationStatus.FUNCTIONAL,
        allowed_tools=frozenset({"search.lead_duplicates"}),
    )
    input_model = LeadSubmission
    output_model = LeadIntakeResult

    async def execute(self, data: LeadSubmission, ctx: ExecutionContext) -> LeadIntakeResult:
        warnings: list[str] = []
        email = normalize_email(data.email)
        phone, region = normalize_phone(data.phone)
        if data.phone and phone is None:
            warnings.append("phone number could not be validated and was discarded")
        if not email and not phone:
            raise DomainValidationError("lead has no valid email or phone after normalization")

        keys = dedupe_keys(email, phone)
        lead = NormalizedLead(
            lead_id=uuid.uuid4().hex,
            tenant_id=ctx.tenant_id,
            full_name=data.full_name,
            email=email,
            phone_e164=phone,
            phone_region=region,
            source=data.source,
            message=data.message,
            budget_min_aed=data.budget_min_aed,
            budget_max_aed=data.budget_max_aed,
            preferred_locations=[normalize_location(loc) for loc in data.preferred_locations],
            property_types=data.property_types,
            bedrooms=data.bedrooms,
            purpose=data.purpose,
            timeline_months=data.timeline_months,
            consent_marketing=data.consent_marketing,
            consent_whatsapp=data.consent_whatsapp,
            external_ref=data.external_ref,
            dedupe_keys=keys,
        )

        result = await self.use_tool(
            ctx, "search.lead_duplicates", {"tenant_id": ctx.tenant_id, "dedupe_keys": keys}
        )
        duplicates = [m["lead_id"] for m in result.data.get("matches", [])]
        if duplicates:
            lead = lead.model_copy(update={"status": LeadStatus.DUPLICATE})
        return LeadIntakeResult(
            lead=lead, is_duplicate=bool(duplicates), duplicate_of=duplicates, warnings=warnings
        )
