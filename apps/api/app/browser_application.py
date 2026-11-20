"""Explicit opt-in composition for same-origin browser account routes.

Call before application startup with reviewed service instances. This module
does not construct databases, Redis clients, Google clients, or a default app.
Existing API routes retain their existing authorization requirements.
"""

import hmac
from typing import cast

from fastapi import APIRouter, Depends, FastAPI, Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Match

from apps.api.app.api.v1.routes.account_google import create_google_auth_router
from apps.api.app.api.v1.routes.accounts import AccountActor, AccountService, create_accounts_router
from apps.api.app.dependencies.account_browser import create_browser_session_transport
from core.security.account_contracts import Dependency
from core.security.google_oauth_flows import GoogleOAuthFlowStore
from core.security.google_oidc import GoogleOIDC
from database.repositories.account_authentication import AccountAuthentication
from database.repositories.account_sessions import AccountSessions


def install_browser_auth(
    app: FastAPI,
    *,
    enabled: bool = False,
    trusted_origin: str | None = None,
    csrf_secret: bytes | None = None,
    oauth_session_secret: str | None = None,
    organization_dependency: Dependency | None = None,
    provider: GoogleOIDC | None = None,
    authentication: AccountAuthentication | None = None,
    sessions: AccountSessions | None = None,
    flow_store: GoogleOAuthFlowStore | None = None,
    account_service: AccountService | None = None,
    rate_guard: Dependency | None = None,
    allow_local_http: bool = False,
) -> bool:
    if type(enabled) is not bool:
        raise ValueError("explicit browser authentication setting required")
    if not enabled:
        return False
    if app.middleware_stack is not None:
        raise ValueError("install browser authentication before startup")
    if getattr(app.state, "browser_auth_installed", False):
        raise ValueError("browser authentication already installed")
    if any(cast(object, item.cls) is SessionMiddleware for item in app.user_middleware):
        raise ValueError("existing session middleware requires explicit review")
    if not isinstance(oauth_session_secret, str) or len(oauth_session_secret.encode()) < 32:
        raise ValueError("dedicated OAuth session secret of at least 32 bytes required")
    if isinstance(csrf_secret, bytes) and hmac.compare_digest(
        oauth_session_secret.encode(), csrf_secret
    ):
        raise ValueError("OAuth and CSRF secrets must be distinct")
    if not callable(organization_dependency) or not callable(rate_guard):
        raise ValueError("trusted organization routing and rate guard required")
    for service, methods in (
        (provider, ("start",)),
        (authentication, ("login_google",)),
        (sessions, ("verify", "revoke")),
        (flow_store, ("reserve", "consume")),
        (
            account_service,
            ("owner_subject", "get_self", "list_pending", "decide", "require_dashboard_access"),
        ),
    ):
        if not all(callable(getattr(service, name, None)) for name in methods):
            raise ValueError("complete reviewed browser authentication services required")

    async def get_provider() -> GoogleOIDC | None:
        return provider

    async def get_authentication() -> AccountAuthentication | None:
        return authentication

    async def get_sessions() -> AccountSessions | None:
        return sessions

    async def get_flow_store() -> GoogleOAuthFlowStore | None:
        return flow_store

    async def get_account_service() -> AccountService | None:
        return account_service

    async def no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"

    transport = create_browser_session_transport(
        trusted_origin=trusted_origin,
        csrf_secret=csrf_secret,
        actor_factory=AccountActor,
        get_organization=organization_dependency,
        get_sessions=get_sessions,
        rate_guard=rate_guard,
        allow_local_http=allow_local_http,
    )
    # The transport constructor above validates the exact origin before use.
    trusted_origin = cast(str, trusted_origin)
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(no_store)])
    router.include_router(
        create_google_auth_router(
            get_organization=organization_dependency,
            get_provider=get_provider,
            get_authentication=get_authentication,
            get_flow_store=get_flow_store,
            rate_guard=rate_guard,
            allow_local_http=allow_local_http,
        )
    )
    router.include_router(transport["router"])
    router.include_router(
        create_accounts_router(
            get_actor=transport["get_actor"],
            get_service=get_account_service,
        )
    )
    reserved = (
        ("GET", "/api/v1/auth/google/start"),
        ("GET", "/api/v1/auth/google/callback"),
        ("GET", "/api/v1/auth/browser/csrf"),
        ("POST", "/api/v1/auth/browser/logout"),
        ("GET", "/api/v1/accounts/me"),
        ("GET", "/api/v1/accounts/approvals/pending"),
        ("POST", "/api/v1/accounts/00000000-0000-0000-0000-000000000001/approval"),
    )
    for method, path in reserved:
        scope = {"type": "http", "method": method, "path": path, "root_path": ""}
        if any(route.matches(scope)[0] is Match.FULL for route in app.routes):
            raise ValueError("browser route conflicts with an existing route")
    # All validation precedes application mutation.
    app.add_middleware(
        SessionMiddleware,
        secret_key=oauth_session_secret,
        session_cookie="__Host-account_oauth"
        if not allow_local_http or trusted_origin.startswith("https:")
        else "account_oauth_local",
        max_age=600,
        path="/",
        same_site="lax",
        https_only=trusted_origin.startswith("https:"),
    )
    app.include_router(router)
    app.state.browser_auth_installed = True
    return True
