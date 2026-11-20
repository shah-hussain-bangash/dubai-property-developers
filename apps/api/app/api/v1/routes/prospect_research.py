"""Local PostgreSQL research workspace. No collection, inference or delivery tools."""

import json
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from apps.api.app.api.v1.routes.leads import _require_isolated_demo
from apps.api.app.api.v1.routes.prospect_batches import router as batch_router
from apps.api.app.api.v1.routes.prospect_replies import router as reply_router
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.prospect_discovery import (
    DiscoveryLimit,
    DiscoveryRequest,
    DiscoveryResponse,
    DiscoveryUnavailable,
    configured,
    reserve_search,
    search_once,
)
from core.prospect_reports import (
    UnsupportedReportText,
    prospect_batch_pdf,
    prospect_pdf,
    prospect_zip,
)
from core.security.rbac import Permission, Principal
from database.prospect_research import RevisionConflict, UnknownOrganization, access_database
from schemas.prospect_research import ResearchWorkspace, WorkspaceWrite
from workflows.runtime import PlatformRuntime

router = APIRouter(prefix="/prospect-research", tags=["local-prospect-research"])
report_gate = BoundedSemaphore(1)


class ReportBusy(Exception):
    pass


def render_report(
    workspace: ResearchWorkspace,
    revision: int,
    prospect_id: str | None = None,
    combined: bool = False,
) -> bytes:
    if not report_gate.acquire(blocking=False):
        raise ReportBusy()
    try:
        if combined:
            return prospect_batch_pdf(workspace, revision)
        if prospect_id is None:
            return prospect_zip(workspace, revision)
        record = next(p for p in workspace.prospects if p.id == prospect_id)
        return prospect_pdf(record, revision)
    finally:
        report_gate.release()


def enabled(runtime: PlatformRuntime) -> None:
    _require_isolated_demo(runtime)
    if not runtime.settings.prospect_storage_enabled:
        raise HTTPException(404, "Prospect database storage is disabled")


async def parse_write(request: Request) -> WorkspaceWrite:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2_000_000:
            raise HTTPException(413, "Workspace exceeds the local storage request limit")
    try:
        return WorkspaceWrite.model_validate(json.loads(raw))
    except Exception:
        raise HTTPException(
            422,
            "Workspace validation failed. Check source URLs, field formats, record limits and duplicates.",
        ) from None


async def execute(
    runtime: PlatformRuntime, principal: Principal, body: WorkspaceWrite | None = None
) -> dict[str, Any]:
    try:
        return {
            "storage": "postgresql",
            "outreach_enabled": False,
            **await access_database(runtime.settings, principal.tenant_id, body),
        }
    except RevisionConflict:
        raise HTTPException(409, "Workspace changed. Reload before making another edit.") from None
    except UnknownOrganization:
        raise HTTPException(
            503, "The active organization is unavailable. No workspace was saved."
        ) from None
    except Exception:
        raise HTTPException(
            503,
            "Prospect database is unavailable. No browser fallback was used; reload to check the last saved state.",
        ) from None


@router.get("/workspace")
async def read(
    response: Response,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> dict[str, Any]:
    enabled(runtime)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal)


@router.put("/workspace")
async def write(
    request: Request,
    response: Response,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_WRITE)),
) -> dict[str, Any]:
    enabled(runtime)
    # Browser writes must come from an explicitly configured local dashboard origin.
    origin = request.headers.get("origin")
    if origin is not None and origin not in runtime.settings.cors_allowed_origins:
        raise HTTPException(403, "Dashboard origin is not allowed")
    body = await parse_write(request)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal, body)


async def report_response(
    runtime: PlatformRuntime,
    principal: Principal,
    revision: int,
    prospect_id: str | None = None,
    combined: bool = False,
) -> Response:
    enabled(runtime)
    snapshot = await execute(runtime, principal)
    if snapshot["revision"] != revision:
        raise HTTPException(409, "Workspace changed. Reload before downloading reports.")
    workspace = ResearchWorkspace.model_validate(snapshot["workspace"])
    if prospect_id is None and not workspace.prospects:
        raise HTTPException(409, "No saved prospects to export.")
    if prospect_id is not None and not any(p.id == prospect_id for p in workspace.prospects):
        raise HTTPException(404, "Prospect not found in this organization.")
    try:
        if combined:
            data = await run_in_threadpool(render_report, workspace, revision, prospect_id, True)
        else:
            data = await run_in_threadpool(render_report, workspace, revision, prospect_id)
    except ReportBusy:
        raise HTTPException(
            429, "Another report is being generated. Try again after it finishes."
        ) from None
    except UnsupportedReportText:
        raise HTTPException(
            422,
            "A record contains text that the current PDF font cannot faithfully display. Use the JSON backup; additional font and script support is needed.",
        ) from None
    except Exception:
        raise HTTPException(
            503, "Report generation could not finish. No records were changed."
        ) from None
    date = datetime.now(timezone(timedelta(hours=4))).strftime("%Y-%m-%d")
    filename = (
        f"prospect-batch-{date}.pdf"
        if combined
        else f"prospect-{prospect_id}-{date}.pdf"
        if prospect_id
        else f"prospect-reports-{date}.zip"
    )
    return Response(
        data,
        media_type="application/pdf" if prospect_id or combined else "application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/reports.pdf")
async def combined_report(
    revision: int = Query(ge=0),
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> Response:
    return await report_response(runtime, principal, revision, combined=True)


@router.get("/reports.zip")
async def zip_reports(
    revision: int = Query(ge=0),
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> Response:
    return await report_response(runtime, principal, revision)


@router.get("/reports/{prospect_id}.pdf")
async def pdf_report(
    prospect_id: str = Path(pattern=r"^[a-zA-Z0-9-]{1,80}$"),
    revision: int = Query(ge=0),
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> Response:
    return await report_response(runtime, principal, revision, prospect_id)


@router.get("/discovery-capabilities")
async def discovery_capabilities(
    response: Response,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
) -> dict[str, Any]:
    enabled(runtime)
    response.headers["Cache-Control"] = "no-store"
    return {
        "enabled": configured(runtime.settings),
        "provider": runtime.settings.prospect_search_provider,
        "daily_limit": runtime.settings.prospect_search_daily_limit,
        "automatic_collection": False,
        "outreach_enabled": False,
    }


@router.post("/discover")
async def discover(
    body: DiscoveryRequest,
    request: Request,
    response: Response,
    runtime: PlatformRuntime = Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_WRITE)),
) -> DiscoveryResponse:
    enabled(runtime)
    origin = request.headers.get("origin")
    if origin is not None and origin not in runtime.settings.cors_allowed_origins:
        raise HTTPException(403, "Dashboard origin is not allowed")
    if not configured(runtime.settings):
        raise HTTPException(503, "Search provider is not connected. No search request was made.")
    try:
        await reserve_search(runtime.settings, principal.tenant_id)
        result = await search_once(runtime.settings, body)
    except DiscoveryLimit:
        raise HTTPException(
            429, "Daily search-attempt limit reached. No provider request was made."
        ) from None
    except DiscoveryUnavailable:
        raise HTTPException(
            503,
            "Search could not finish. No contacts were saved. Do not retry automatically; attempts may use provider credits.",
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return result


# Batch endpoints share the same local research storage and permission gates.

router.include_router(batch_router)

router.include_router(reply_router)
