"""Account approval routes with injected authentication and service.

Not mounted automatically. Authentication must supply verified user and
organization identifiers. The service must recheck current account/organization
state, enforce conditional decisions, and commit decisions and audit atomically.
The service's owner identity must come from trusted server configuration.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictBool


@dataclass(frozen=True, slots=True)
class AccountActor:
    user_id: UUID
    organization_id: UUID

    def __post_init__(self):
        if not isinstance(self.user_id, UUID) or not isinstance(self.organization_id, UUID):
            raise ValueError("verified UUID identifiers required")


class AccountView(BaseModel):
    account_id: UUID
    organization_id: UUID
    full_name: str
    approval_status: Literal["pending", "approved", "rejected"] | None


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: StrictBool


class AccountService(Protocol):
    def owner_subject(self, organization_id: UUID) -> UUID | None: ...
    async def list_pending(self, actor: AccountActor, *, limit: int) -> list[dict]: ...
    async def decide(self, actor: AccountActor, target_id: UUID, *, approve: bool) -> dict: ...
    async def get_self(self, actor: AccountActor) -> dict: ...


async def _unconfigured_actor():
    raise HTTPException(status_code=401, detail="authentication required")


async def _unconfigured_service():
    raise HTTPException(status_code=503, detail="account service unavailable")


def create_accounts_router(
    *,
    get_actor: Callable = _unconfigured_actor,
    get_service: Callable = _unconfigured_service,
) -> APIRouter:
    router = APIRouter(prefix="/accounts", tags=["accounts"])

    def owner_required(actor, service):
        owner = service.owner_subject(actor.organization_id)
        if not isinstance(owner, UUID) or owner != actor.user_id:
            raise HTTPException(status_code=403, detail="owner approval required")

    def checked_view(data, actor, expected_id=None, expected_status=None):
        view = AccountView.model_validate(data)
        if view.organization_id != actor.organization_id:
            raise HTTPException(status_code=403, detail="account access denied")
        if expected_id is not None and view.account_id != expected_id:
            raise HTTPException(status_code=403, detail="account access denied")
        if expected_status is not None and view.approval_status != expected_status:
            raise HTTPException(status_code=503, detail="account service inconsistency")
        return view

    @router.get("/me", response_model=AccountView)
    async def get_me(
        actor: AccountActor = Depends(get_actor),
        service: AccountService = Depends(get_service),
    ):
        # This exposes only own account status, not protected dashboard data.
        return checked_view(await service.get_self(actor), actor, expected_id=actor.user_id)

    @router.get("/approvals/pending", response_model=list[AccountView])
    async def list_pending(
        limit: int = Query(default=50, ge=1, le=100),
        actor: AccountActor = Depends(get_actor),
        service: AccountService = Depends(get_service),
    ):
        owner_required(actor, service)
        rows = await service.list_pending(actor, limit=limit)
        if len(rows) > limit:
            raise HTTPException(status_code=503, detail="account service inconsistency")
        return [checked_view(row, actor, expected_status="pending") for row in rows]

    @router.post("/{account_id}/approval", response_model=AccountView)
    async def decide(
        account_id: UUID,
        body: ApprovalDecision,
        actor: AccountActor = Depends(get_actor),
        service: AccountService = Depends(get_service),
    ):
        owner_required(actor, service)
        if account_id == actor.user_id:
            raise HTTPException(status_code=403, detail="self-approval prohibited")
        row = await service.decide(actor, account_id, approve=body.approve)
        return checked_view(
            row,
            actor,
            expected_id=account_id,
            expected_status="approved" if body.approve else "rejected",
        )

    return router
