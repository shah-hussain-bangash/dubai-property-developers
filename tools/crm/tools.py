"""CRM tools (delegate to the configured ``CRMClient``: mock or EspoCRM)."""

from __future__ import annotations

from typing import Any, ClassVar

from core.exceptions.errors import DomainValidationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from integrations.espocrm.client import CRMClient
from tools.base import BaseTool, ToolSpec


class CRMFindLeadsTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.find_leads",
        description="Find CRM leads by email or E.164 phone",
        category=ActionCategory.READ,
        permission=Permission.LEADS_READ,
    )

    def __init__(self, client: CRMClient) -> None:
        self._client = client

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        leads = await self._client.find_leads(email=payload.get("email"), phone=payload.get("phone"))
        return {"leads": leads}


class CRMCreateLeadTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.create_lead",
        description="Create a lead record in the CRM",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def __init__(self, client: CRMClient) -> None:
        self._client = client

    def validate(self, payload: dict[str, Any]) -> None:
        data = payload.get("data") or {}
        if not data.get("lastName") and not data.get("name"):
            raise DomainValidationError("CRM lead requires a name")
        if not data.get("emailAddress") and not data.get("phoneNumber"):
            raise DomainValidationError("CRM lead requires email or phone")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        external_id = await self._client.create_lead(
            payload["data"], idempotency_key=str(payload["local_lead_id"])
        )
        return {"external_id": external_id}


class CRMUpdateLeadTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.update_lead",
        description="Update fields on an existing CRM lead",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def __init__(self, client: CRMClient) -> None:
        self._client = client

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._client.update_lead(payload["external_id"], payload["data"])
        return {"external_id": payload["external_id"], "updated": True}


class CRMAddNoteTool(BaseTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.add_note",
        description="Append an activity note to a CRM record",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def __init__(self, client: CRMClient) -> None:
        self._client = client

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        note_id = await self._client.add_note(
            parent_type=payload.get("parent_type", "Lead"),
            parent_id=payload["parent_id"],
            text=payload["text"],
        )
        return {"note_id": note_id}
