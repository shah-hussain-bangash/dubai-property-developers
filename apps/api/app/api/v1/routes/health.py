"""Liveness (/health) and readiness (/ready) probes - unauthenticated, not rate limited."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.api.app.dependencies.runtime import get_app_settings, get_runtime
from core.cache.redis import ping_redis
from core.config.settings import Settings
from database.sessions.engine import create_engine, ping_database
from workflows.runtime import PlatformRuntime

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class DependencyCheck(BaseModel):
    name: str
    status: Literal["ok", "unavailable", "skipped"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready", "degraded"]
    checks: list[DependencyCheck]
    agents_registered: int


async def _check_database(settings: Settings) -> bool:
    """Keep database probe failures from hiding the other readiness checks."""
    engine = None
    healthy = False
    try:
        engine = create_engine(settings)
        healthy = bool(await ping_database(engine))
    except Exception:
        healthy = False
    finally:
        if engine is not None:
            try:
                await engine.dispose()
            except Exception:
                healthy = False
    return healthy


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    settings: Settings = Depends(get_app_settings),
    runtime: PlatformRuntime = Depends(get_runtime),
) -> JSONResponse:
    checks: list[DependencyCheck] = []
    if settings.readiness_checks_required:
        db_ok = await _check_database(settings)
        redis_ok = await ping_redis(settings)
        checks.append(DependencyCheck(name="postgres", status="ok" if db_ok else "unavailable"))
        checks.append(DependencyCheck(name="redis", status="ok" if redis_ok else "unavailable"))
    else:
        checks.append(DependencyCheck(name="postgres", status="skipped"))
        checks.append(DependencyCheck(name="redis", status="skipped"))

    failing = any(c.status == "unavailable" for c in checks)
    status = (
        "not_ready" if failing else ("ready" if settings.readiness_checks_required else "degraded")
    )
    body = ReadinessResponse(status=status, checks=checks, agents_registered=len(runtime.agents))
    return JSONResponse(status_code=503 if failing else 200, content=body.model_dump())
