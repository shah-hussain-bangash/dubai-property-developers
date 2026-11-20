from __future__ import annotations

from typing import Any, ClassVar

from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from schemas.leads.models import NormalizedLead
from tools.base import BaseTool, ToolSpec
from tools.search.lead_store import LeadStore


class LeadDuplicateSearchTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="search.lead_duplicates",
        description="Find existing platform leads sharing a dedupe key (email/phone)",
        category=ActionCategory.READ,
        permission=Permission.LEADS_READ,
    )

    def __init__(self, store: LeadStore) -> None:
        self._store = store

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        matches = await self._store.find_by_dedupe_keys(
            payload["tenant_id"], payload["dedupe_keys"]
        )
        return {"matches": [m.model_dump(mode="json") for m in matches]}


class LeadSaveTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="leads.save",
        description="Persist a normalized lead in the platform lead store",
        category=ActionCategory.INTERNAL_WRITE,
        permission=Permission.LEADS_WRITE,
    )

    def __init__(self, store: LeadStore) -> None:
        self._store = store

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        lead = NormalizedLead.model_validate(payload["lead"])
        await self._store.save(lead)
        return {"lead_id": lead.lead_id, "status": lead.status.value}
