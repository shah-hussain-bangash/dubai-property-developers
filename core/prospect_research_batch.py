"""Checkpointed source-discovery engine. Not registered with an API or scheduler.

Each advance makes at most one provider request. Persist checkpoints durably before
calling again; the caller must serialize advances per batch. No contact delivery.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from core.prospect_discovery import (
    DiscoveryLimit,
    DiscoveryRequest,
    DiscoveryUnavailable,
    configured,
    reserve_search,
    safe_result_url,
    search_once,
)

Scope = Literal["web", "linkedin", "facebook", "instagram"]
Status = Literal[
    "ready",
    "paused",
    "quota_wait",
    "request_uncertain",
    "completed",
    "queries_exhausted",
    "cancelled",
    "error",
]
ROLES = {
    "ceo": "CEO",
    "director": "director",
    "entrepreneur": "entrepreneur",
    "investor": "investor",
    "agent": "real estate agent",
    "business_owner": "business owner",
}


class BatchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["ceo", "director", "entrepreneur", "investor", "agent", "business_owner"]
    query: str = Field(min_length=3, max_length=300)
    scope: Scope = "web"


class SourceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{24}$")
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=1500)
    snippet: str = Field(max_length=1000)
    search_query: str = Field(max_length=300)
    query_role: str = Field(max_length=30)
    discovered_at: AwareDatetime


class ResearchBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,80}$")
    tenant_id: str = Field(min_length=1, max_length=100)
    target: int = Field(default=500, ge=1, le=500)
    queries: list[BatchQuery] = Field(min_length=1, max_length=100)
    cursor: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0, le=100)
    status: Status = "ready"
    resume_at: AwareDatetime | None = None
    candidates: list[SourceCandidate] = Field(default_factory=list, max_length=500)
    notice: str = Field(default="", max_length=250)

    @model_validator(mode="after")
    def validate_progress(self):
        if (
            self.cursor > len(self.queries)
            or self.provider_attempts > self.cursor
            or len(self.candidates) > self.target
        ):
            raise ValueError("Invalid batch progress")
        if len({q.query.lower().strip() + "|" + q.scope for q in self.queries}) != len(
            self.queries
        ):
            raise ValueError("Duplicate query")
        if len({p.id for p in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate candidate")
        for p in self.candidates:
            if not safe_result_url(p.url, "web") or source_id(p.url) != p.id:
                raise ValueError("Invalid public source")
        if self.status == "completed" and len(self.candidates) != self.target:
            raise ValueError("Target is not complete")
        if self.status == "quota_wait" and self.resume_at is None:
            raise ValueError("Missing quota resume time")
        return self


def source_id(url):
    parts = urlsplit(url)
    canonical = urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
    )
    return sha256(canonical.encode()).hexdigest()[:24]


def new_batch(batch_id, tenant_id, location="Dubai", scope: Scope = "linkedin", target=500):
    location = location.strip()
    if not location or len(location) > 100:
        raise ValueError("Enter a location up to 100 characters")
    queries = [
        BatchQuery(role=role, query=f"{location} {label} public business profile", scope=scope)
        for role, label in ROLES.items()
    ]
    return ResearchBatch(id=batch_id, tenant_id=tenant_id, target=target, queries=queries)


def transition(
    batch: ResearchBatch,
    tenant_id: str,
    action: Literal["pause", "resume", "cancel", "skip_uncertain"],
):
    if batch.tenant_id != tenant_id:
        raise ValueError("Batch tenant mismatch")
    value = batch.model_copy(deep=True)
    if action == "cancel":
        value.status = "cancelled"
        value.resume_at = None
        value.notice = "Cancelled; existing source candidates retained."
    elif action == "pause" and batch.status in {"ready", "quota_wait"}:
        value.status = "paused"
        value.notice = "Paused; no source request initiated."
    elif action == "resume" and batch.status == "paused":
        value.status = "quota_wait" if value.resume_at else "ready"
        value.notice = "Resumed; quota still applies."
    elif action == "skip_uncertain" and batch.status == "request_uncertain":
        value.status = "ready"
        value.notice = (
            "Uncertain query skipped without retry; a provider credit may have been used."
        )
    else:
        raise ValueError("Unsupported batch transition")
    return ResearchBatch.model_validate(value.model_dump())


async def advance_batch(
    batch: ResearchBatch,
    settings,
    tenant_id: str,
    checkpoint: Callable[[dict], Awaitable[None]],
    now=None,
):
    """Return new state only after awaited checkpoints; caller persists/locks it.

    No loop, scheduler, page fetching, contact inference, messaging or calling.
    request_uncertain is persisted before the provider call; crash recovery never
    retries it automatically. The query cursor is advanced before that request.
    """
    if batch.tenant_id != tenant_id:
        raise ValueError("Batch tenant mismatch")
    stamp = now or datetime.now(UTC)
    if stamp.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    value = ResearchBatch.model_validate(batch.model_dump())
    if value.status not in {"ready", "quota_wait"}:
        return value
    if value.resume_at and stamp < value.resume_at:
        return value

    async def save():
        await checkpoint(ResearchBatch.model_validate(value.model_dump()).model_dump(mode="json"))

    if len(value.candidates) >= value.target:
        value.status = "completed"
        value.resume_at = None
        await save()
        return value
    if value.cursor >= len(value.queries):
        value.status = "queries_exhausted"
        value.resume_at = None
        value.notice = "Queries exhausted; partial source results retained. Target not guaranteed."
        await save()
        return value
    if not configured(settings):
        raise ValueError("Search provider is not configured")
    query = value.queries[value.cursor]
    try:
        await reserve_search(settings, tenant_id)
    except DiscoveryLimit:
        local = stamp.astimezone(timezone(timedelta(hours=4)))
        value.resume_at = (local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        value.status = "quota_wait"
        value.notice = (
            "Daily quota reached. No provider request made; wait until the next Dubai day."
        )
        await save()
        return value
    except DiscoveryUnavailable:
        value.status = "error"
        value.notice = "Quota service unavailable; no provider request initiated."
        await save()
        return value
    value.cursor += 1
    value.provider_attempts += 1
    value.status = "request_uncertain"
    value.resume_at = None
    value.notice = "Provider outcome not yet checkpointed. Do not automatically retry this query."
    await save()  # Fail closed: no provider request if durable storage fails.
    try:
        result = await search_once(settings, DiscoveryRequest(query=query.query, scope=query.scope))
        if (
            result.get("provider") != "serpapi"
            or result.get("engine") != "google"
            or result.get("query") != query.query
            or result.get("scope") != query.scope
            or any(
                result.get(k) is not False
                for k in ("contacts_saved", "outreach_enabled", "automatic_collection")
            )
        ):
            raise ValueError("Unexpected source response")
        rows = result.get("results")
        if not isinstance(rows, list) or len(rows) > 10:
            raise ValueError("Invalid source result count")
        found = []
        seen = {p.id for p in value.candidates}
        for row in rows:
            url = safe_result_url(row.get("url"), query.scope)
            if not url:
                raise ValueError("Invalid public source URL")
            identifier = source_id(url)
            if identifier in seen:
                continue
            found.append(
                SourceCandidate(
                    id=identifier,
                    title=row["title"],
                    url=url,
                    snippet=row["snippet"],
                    search_query=query.query,
                    query_role=query.role,
                    discovered_at=stamp,
                )
            )
            seen.add(identifier)
        value.candidates.extend(found[: max(0, value.target - len(value.candidates))])
        value.status = (
            "completed"
            if len(value.candidates) >= value.target
            else "queries_exhausted"
            if value.cursor >= len(value.queries)
            else "ready"
        )
        value.notice = "Public source candidates saved for review. No verified contacts or buying ability inferred."
    except Exception:
        # Never copy provider errors or response bodies into saved state.
        value.notice = (
            "Request outcome could not be confirmed. Existing sources retained; no automatic retry."
        )
        await save()
        return value
    await save()
    return value
