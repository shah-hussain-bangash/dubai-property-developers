"""Add owner-managed knowledge to the existing private read-only AWS app.

The private startup module and its verifier stay on the server unchanged.
Only the assigned-source router receives workflow-manager authority; every
other request and the single runtime lifespan use the original application.
"""

from dataclasses import replace
from importlib import import_module
from typing import cast

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from apps.api.app.api.v1.routes.agent_knowledge import router
from apps.api.app.dependencies.auth import TokenVerifier
from apps.api.app.exception_handlers.handlers import register_exception_handlers
from apps.api.app.middleware.correlation import CorrelationIdMiddleware
from apps.api.app.middleware.error_response import ErrorResponseMiddleware
from apps.api.app.middleware.rate_limit import InMemoryFixedWindowRateLimiter, RateLimitMiddleware
from apps.api.app.middleware.security_headers import SecurityHeadersMiddleware
from core.security.rbac import Principal, Role


class KnowledgeVerifier:
    def __init__(self, original: TokenVerifier) -> None:
        self.original = original

    async def verify(self, token: str) -> Principal:
        principal = await self.original.verify(token)
        return replace(principal, roles=frozenset({Role.SALES_MANAGER}))


def build_gateway(original: FastAPI) -> ASGIApp:
    sources = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sources.state.settings = original.state.settings
    sources.state.runtime = original.state.runtime
    sources.state.token_verifier = KnowledgeVerifier(original.state.token_verifier)
    sources.add_middleware(
        RateLimitMiddleware,
        limiter=InMemoryFixedWindowRateLimiter(original.state.settings.rate_limit_per_minute),
    )
    sources.add_middleware(ErrorResponseMiddleware)
    sources.add_middleware(SecurityHeadersMiddleware)
    sources.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(sources)
    sources.include_router(router, prefix="/api/v1")

    async def dispatch(scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (
            path == "/api/v1/knowledge/agents" or path.startswith("/api/v1/knowledge/agents/")
        ):
            await sources(scope, receive, send)
        else:
            await original(scope, receive, send)

    return dispatch


def create_private_gateway() -> ASGIApp:
    # This existing, read-only bind mount is never exported or rewritten.
    original = cast(FastAPI, import_module("step660_api_entry").app)
    return build_gateway(original)
