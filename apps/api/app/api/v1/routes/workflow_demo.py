"""Compose existing isolated demos into a fictional lead-to-draft scenario."""

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.api.app.api.v1.routes.conversation_demo import DemoConversationMessage, demo_draft
from apps.api.app.api.v1.routes.leads import _require_isolated_demo, demo_process
from apps.api.app.api.v1.routes.property_demo import DemoPropertyCriteria, demo_recommendations
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.security.rbac import Permission, Principal
from schemas.leads.models import LeadSubmission
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/workflows", tags=["development-only"])


class DemoScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: UUID
    budget: Decimal = Field(gt=0, le=10000000000)
    location: Literal["Business Bay", "Dubai Marina", "Jumeirah Village Circle"]
    bedrooms: int = Field(ge=0, le=5, strict=True)


@router.post("/demo-scenario", summary="[DEV ONLY] Fictional lead-to-draft scenario")
async def demo_scenario(
    body: DemoScenario,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.WORKFLOWS_EXECUTE)),
) -> dict[str, Any]:
    _require_isolated_demo(runtime)
    if body.scenario_id.int == 0:
        raise HTTPException(status_code=422, detail="A demo scenario identity is required")
    lead = await demo_process(
        LeadSubmission(
            full_name="Fictional Workflow Demo",
            email=f"demo-{body.scenario_id.hex}@example.com",
            source="website",
            message="Fictional demo enquiry: requesting a property viewing.",
            budget_max_aed=body.budget,
            preferred_locations=[body.location],
            property_types=["apartment"],
            bedrooms=body.bedrooms,
            purpose="investment",
            timeline_months=3,
            consent_marketing=False,
            consent_whatsapp=False,
        ),
        runtime,
        principal,
    )
    if lead.status != "succeeded" or lead.error is not None:
        raise HTTPException(status_code=503, detail="Demo qualification unavailable")
    result = {
        "dev_only": True,
        "uses_mock_integrations": True,
        "source": "fictional-guided-demo",
        "status": "duplicate",
        "lead": lead.model_dump(mode="json"),
        "properties": None,
        "reply": None,
    }
    if lead.result["is_duplicate"]:
        return result
    crm = lead.result.get("crm") or {}
    if not str(crm.get("external_id", "")).startswith("mock-lead-"):
        raise HTTPException(status_code=503, detail="Mock lead result unavailable")
    properties = await demo_recommendations(
        DemoPropertyCriteria(
            budget_max_aed=body.budget,
            locations=[body.location],
            bedrooms_min=body.bedrooms,
            bedrooms_max=body.bedrooms,
            property_types=["apartment"],
            limit=3,
        ),
        runtime,
        principal,
    )
    result["properties"] = properties
    if not properties["output"]["recommendations"]:
        result["status"] = "no_matches"
        return result
    result["reply"] = await demo_draft(
        DemoConversationMessage(message="Please arrange a viewing"), runtime, principal
    )
    result["status"] = "completed"
    return result
