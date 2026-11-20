"""Authentication and authorization dependencies.

* ``AUTH_MODE=dev`` (development/test only): a development principal is injected.
  Roles may be overridden with the ``X-Dev-Roles`` header to exercise RBAC.
* ``AUTH_MODE=token``: a ``TokenVerifier`` must be registered on
  ``app.state.token_verifier`` (OIDC/JWT verification is planned). Without one,
  every protected request is rejected with 401 - fail closed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import Depends, Request

from core.config.settings import AuthMode, Settings
from core.exceptions.errors import AuthenticationError, AuthorizationError
from core.security.rbac import Permission, Principal, Role


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Principal: ...


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def get_principal(request: Request) -> Principal:
    settings = _settings(request)
    if settings.auth_mode == AuthMode.DEV:
        if not settings.is_dev_like:
            raise AuthenticationError("dev authentication is disabled in this environment")
        roles = {Role.SALES_MANAGER}
        override = request.headers.get("X-Dev-Roles")
        if override:
            try:
                roles = {Role(r.strip()) for r in override.split(",") if r.strip()}
            except ValueError as exc:
                raise AuthenticationError("unknown role in X-Dev-Roles") from exc
        return Principal(
            subject="dev-user",
            tenant_id=settings.default_tenant_id,
            roles=frozenset(roles),
            display_name="Development User",
        )

    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise AuthenticationError("bearer token required")
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise AuthenticationError("token verification is not configured")
    return await verifier.verify(header[7:].strip())


def require_permission(permission: Permission) -> Callable[..., Awaitable[Principal]]:
    async def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise AuthorizationError(f"missing permission {permission.value}")
        return principal

    return _dependency
