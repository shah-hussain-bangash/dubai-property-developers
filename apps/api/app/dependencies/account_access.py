"""Account dependencies awaiting trusted application composition.

The supplied principal dependency must perform actual token verification.
Identity subjects and tenant IDs must be internal UUID strings. External OIDC
subjects require a trusted server-side identity mapping before this adapter.
No application registration, engine creation, or token verification is installed.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, Request


def build_account_dependencies(*, principal_dependency, actor_factory):
    if not callable(principal_dependency) or not callable(actor_factory):
        raise ValueError("trusted principal dependency and actor factory required")

    async def verified_principal(request: Request):
        settings = getattr(request.app.state, "settings", None)
        mode = getattr(settings, "auth_mode", None)
        if getattr(mode, "value", mode) != "token":
            raise HTTPException(401, "token authentication required")
        headers = request.headers.getlist("authorization")
        if len(headers) != 1:
            raise HTTPException(401, "bearer token required")
        parts = headers[0].split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(401, "bearer token required")
        verifier = getattr(request.app.state, "token_verifier", None)
        if not callable(getattr(verifier, "verify", None)):
            raise HTTPException(401, "token verification unavailable")
        return await principal_dependency(request)

    async def get_actor(principal=Depends(verified_principal)):
        subject = getattr(principal, "subject", None)
        tenant = getattr(principal, "tenant_id", None)
        try:
            if not isinstance(subject, str) or not isinstance(tenant, str):
                raise ValueError("UUID strings required")
            user_id = UUID(subject)
            organization_id = UUID(tenant)
            if user_id.int == 0 or organization_id.int == 0:
                raise ValueError("nil UUID prohibited")
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(401, "account identity unavailable") from None
        return actor_factory(user_id=user_id, organization_id=organization_id)

    async def get_service():
        raise HTTPException(503, "account service unavailable")

    async def configured_service(request: Request):
        service = getattr(request.app.state, "account_service", None)
        methods = (
            "owner_subject",
            "list_pending",
            "decide",
            "get_self",
            "require_dashboard_access",
        )
        if service is None or not all(
            callable(getattr(service, method, None)) for method in methods
        ):
            return await get_service()
        return service

    async def require_dashboard_access(
        actor=Depends(get_actor),
        service=Depends(configured_service),
    ):
        return await service.require_dashboard_access(actor)

    return {
        "get_actor": get_actor,
        "get_service": configured_service,
        "require_dashboard_access": require_dashboard_access,
    }
