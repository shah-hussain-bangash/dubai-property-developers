"""Explicit manual reply review. No inbox sync, notification delivery or calls."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from apps.api.app.api.v1.routes.prospect_batches import guard
from apps.api.app.dependencies.auth import require_permission
from apps.api.app.dependencies.runtime import get_runtime
from core.prospect_reply_workflow import ReplyEvent
from core.security.rbac import Permission, Principal
from database.prospect_reply_storage import UnknownProspect, access_reply_storage
from database.prospect_research import RevisionConflict, UnknownOrganization

router = APIRouter(prefix="/replies", tags=["local-prospect-replies"])
Identity = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9-]{1,100}$")]


class ManualReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    prospect_id: Identity
    event_id: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9-]{1,80}$")]
    channel: Literal["email", "whatsapp"]
    kind: Literal["reply", "opt_out", "auto_reply", "bounce"]
    received_at: AwareDatetime
    text: str = Field(min_length=1, max_length=10_000)
    confirmed: bool

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Reply text required")
        return value


class CloseCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=1)
    task_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
    status: Literal["completed", "cancelled"]
    note: str = Field(min_length=1, max_length=1500)


async def parse(request, model):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 50_000:
            raise HTTPException(413, "Reply request is too large.")
    try:
        return model.model_validate_json(raw)
    except Exception:
        raise HTTPException(
            422, "Check the reply fields, timezone, classification and confirmation."
        ) from None


def project(saved, principal):
    state = saved["state"]
    return {
        "storage": "postgresql",
        "outreach_enabled": False,
        "inbox_connected": False,
        "notifications_delivered": False,
        "revision": saved["revision"],
        "actor_id": principal.subject,
        "reply_count": len(state["replies"]),
        "notification_count": len(state["notifications"]),
        "pending_count": sum(t["status"] == "needs_review" for t in state["tasks"]),
        "suppressed_prospect_ids": [row["prospect_id"] for row in state["suppressions"]],
        "tasks": [
            {
                **{
                    key: row[key]
                    for key in [
                        "id",
                        "prospect_id",
                        "owner_id",
                        "status",
                        "calling_permission",
                        "created_at",
                        "updated_at",
                    ]
                },
                "completion_note": row["completion_note"][:500],
            }
            for row in state["tasks"]
        ],
        "recent_replies": [
            {
                "id": row["id"],
                "prospect_id": row["prospect_id"],
                "channel": row["event"]["channel"],
                "kind": row["event"]["kind"],
                "received_at": row["event"]["received_at"],
                "text": row["event"]["text"][:500],
            }
            for row in reversed(state["replies"][-50:])
        ],
    }


async def execute(runtime, principal, operation="read", **kwargs):
    try:
        return project(
            await access_reply_storage(runtime.settings, principal.tenant_id, operation, **kwargs),
            principal,
        )
    except RevisionConflict:
        raise HTTPException(
            409, "Reply workspace changed. Reload replies before another action."
        ) from None
    except UnknownProspect:
        raise HTTPException(
            422, "Select a prospect saved in this organization. Reload prospects if needed."
        ) from None
    except UnknownOrganization:
        raise HTTPException(503, "Active organization unavailable.") from None
    except ValueError:
        raise HTTPException(
            422,
            "Reply attribution, task ownership, revision or outcome is invalid. Reload before acting again.",
        ) from None
    except Exception:
        raise HTTPException(
            503, "Reply save could not be confirmed. Keep the draft and reload before any retry."
        ) from None


@router.get("")
async def read_replies(
    response: Response,
    runtime=Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_READ)),
):
    guard(runtime)
    response.headers["Cache-Control"] = "no-store"
    return await execute(runtime, principal)


@router.post("")
async def manual_reply(
    request: Request,
    response: Response,
    runtime=Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_WRITE)),
):
    guard(runtime, request)
    body = await parse(request, ManualReply)
    if body.confirmed is not True:
        raise HTTPException(422, "Confirm the prospect match and reply classification first.")
    if body.received_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(422, "Reply time cannot be in the future.")
    event = ReplyEvent(
        channel=body.channel,
        provider_event_id="manual-" + body.event_id,
        kind=body.kind,
        received_at=body.received_at,
        text=body.text,
    )
    response.headers["Cache-Control"] = "no-store"
    return await execute(
        runtime,
        principal,
        "record",
        revision=body.revision,
        prospect_id=body.prospect_id,
        owner_id=principal.subject,
        event=event,
    )


@router.post("/close-task")
async def close_callback(
    request: Request,
    response: Response,
    runtime=Depends(get_runtime),
    principal: Principal = Depends(require_permission(Permission.LEADS_WRITE)),
):
    guard(runtime, request)
    body = await parse(request, CloseCallback)
    response.headers["Cache-Control"] = "no-store"
    return await execute(
        runtime,
        principal,
        "close",
        revision=body.revision,
        owner_id=principal.subject,
        task_id=body.task_id,
        status=body.status,
        note=body.note,
    )
