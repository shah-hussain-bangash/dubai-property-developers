"""Local batch controls. No scheduler, contact promotion or delivery registration."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from apps.api.app.api.v1.routes.leads import _require_isolated_demo
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.security.rbac import Permission, Principal
from database.prospect_research import RevisionConflict, UnknownOrganization
from database.prospect_research_batches import (
    BatchBusy,
    BatchCapacity,
    BatchNotFound,
    access_batches,
)
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/batches", tags=["local-research-batches"])


class CreateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    location: str = Field(default="Dubai", min_length=1, max_length=100)
    scope: Literal["web", "linkedin", "facebook", "instagram"] = "linkedin"
    target: int = Field(default=500, ge=1, le=500)


class BatchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    action: Literal["advance", "pause", "resume", "cancel", "skip_uncertain"]


def guard(runtime: PlatformRuntime, request: Request | None = None) -> None:
    _require_isolated_demo(runtime)
    if not runtime.settings.prospect_storage_enabled:
        raise HTTPException(404, "Research storage disabled")
    if request is not None:
        origin = request.headers.get("origin")
        if origin is not None and origin not in runtime.settings.cors_allowed_origins:
            raise HTTPException(403, "Dashboard origin is not allowed")


async def execute(
    runtime: PlatformRuntime, principal: Principal, operation: str = "list", **kwargs: Any
) -> dict[str, Any]:
    try:
        value = await access_batches(runtime.settings, principal.tenant_id, operation, **kwargs)
        return {
            "storage": "postgresql",
            "outreach_enabled": False,
            "scheduled": False,
            ("batches" if operation == "list" else "batch"): value,
        }
    except RevisionConflict:
        raise HTTPException(
            409, "Batch changed. Reload before another action; no automatic retry."
        ) from None
    except BatchBusy:
        raise HTTPException(
            409, "This batch is already running a query. Reload later; do not retry automatically."
        ) from None
    except BatchNotFound:
        raise HTTPException(404, "Batch not found in this organization.") from None
    except BatchCapacity:
        raise HTTPException(409, "This organization already has 20 research batches.") from None
    except ValueError:
        raise HTTPException(
            422, "Batch action or search configuration is not valid for this state."
        ) from None
    except UnknownOrganization:
        raise HTTPException(503, "Active organization unavailable.") from None
    except Exception:
        raise HTTPException(
            503,
            "Batch operation could not be confirmed. Reload saved state before another action; no automatic retry.",
        ) from None


@router.get("")
async def list_jobs(
    response: Response,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> dict[str, Any]:
    guard(runtime)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal)


@router.post("")
async def create_job(
    body: CreateBatch,
    request: Request,
    response: Response,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_WRITE)),
) -> dict[str, Any]:
    guard(runtime, request)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal, "create", body=body)


@router.get("/{batch_id}")
async def read_job(
    response: Response,
    batch_id: str = Path(pattern=r"^[a-zA-Z0-9-]{1,80}$"),
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> dict[str, Any]:
    guard(runtime)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal, "read", batch_id=batch_id)


@router.post("/{batch_id}/actions")
async def action_job(
    body: BatchAction,
    request: Request,
    response: Response,
    batch_id: str = Path(pattern=r"^[a-zA-Z0-9-]{1,80}$"),
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_WRITE)),
) -> dict[str, Any]:
    guard(runtime, request)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal, body.action, batch_id=batch_id, revision=body.revision)
