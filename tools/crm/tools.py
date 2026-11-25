"""CRM tools (delegate to the configured ``CRMClient``: mock or EspoCRM)."""

from __future__ import annotations

from typing import Any, ClassVar

from core.exceptions.errors import AuthorizationError, DomainValidationError
from core.policies.actions import ActionCategory
from core.security.rbac import Permission
from integrations.espocrm.client import CRMClient, validate_crm_record_id
from tools.base import BaseTool, ToolCallContext, ToolSpec


class OrganizationCRMTool(BaseTool):
    """One configured account belongs to one explicitly bound organization."""

    def __init__(self, client: CRMClient, *, tenant_id: str | None = None) -> None:
        self._client = client
        self._tenant_id = tenant_id

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._tenant_id is not None:
            raise AuthorizationError("Organization-bound CRM calls require a trusted identity")
        # Compatibility for explicitly constructed, standalone internal adapters.
        self.validate(payload)
        return await self._execute(payload)

    def authorize_context(self, ctx: ToolCallContext) -> None:
        if (
            not self._tenant_id
            or ctx.tenant_id != self._tenant_id
            or ctx.principal.tenant_id != self._tenant_id
        ):
            raise AuthorizationError("CRM account is not configured for this organization")

    async def execute_with_context(
        self, payload: dict[str, Any], ctx: ToolCallContext
    ) -> dict[str, Any]:
        self.authorize_context(ctx)
        self.validate(payload)
        return await self._execute(payload)

    async def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class CRMFindLeadsTool(OrganizationCRMTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.find_leads",
        description="Find CRM leads by email or E.164 phone",
        category=ActionCategory.READ,
        permission=Permission.LEADS_READ,
    )

    async def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        leads = await self._client.find_leads(
            email=payload.get("email"), phone=payload.get("phone")
        )
        return {"leads": leads}


class CRMCreateLeadTool(OrganizationCRMTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.create_lead",
        description="Create a lead record in the CRM",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def validate(self, payload: dict[str, Any]) -> None:
        data = payload.get("data") or {}
        if not data.get("lastName") and not data.get("name"):
            raise DomainValidationError("CRM lead requires a name")
        if not data.get("emailAddress") and not data.get("phoneNumber"):
            raise DomainValidationError("CRM lead requires email or phone")

    async def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        external_id = await self._client.create_lead(
            payload["data"], idempotency_key=str(payload["local_lead_id"])
        )
        return {"external_id": external_id}


class CRMUpdateLeadTool(OrganizationCRMTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.update_lead",
        description="Update fields on an existing CRM lead",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    def validate(self, payload: dict[str, Any]) -> None:
        validate_crm_record_id(payload.get("external_id"))

    async def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._client.update_lead(payload["external_id"], payload["data"])
        return {"external_id": payload["external_id"], "updated": True}


class CRMAddNoteTool(OrganizationCRMTool):
    spec: ClassVar[ToolSpec] = ToolSpec(
        name="crm.add_note",
        description="Append an activity note to a CRM record",
        category=ActionCategory.CRM_WRITE,
        permission=Permission.CRM_WRITE,
    )

    async def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        note_id = await self._client.add_note(
            parent_type=payload.get("parent_type", "Lead"),
            parent_id=payload["parent_id"],
            text=payload["text"],
        )
        return {"note_id": note_id}
