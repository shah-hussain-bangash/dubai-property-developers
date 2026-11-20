from __future__ import annotations

from fastapi import Request

from core.config.settings import Settings
from workflows.runtime import PlatformRuntime


def get_runtime(request: Request) -> PlatformRuntime:
    return request.app.state.runtime  # type: ignore[no-any-return]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]
