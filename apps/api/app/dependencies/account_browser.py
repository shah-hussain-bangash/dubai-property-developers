"""Opt-in browser session transport; no live application mounting.

Inject AccountSessions, trusted organization routing, an actor factory, a
rate guard, and a dedicated shared CSRF signing secret. Browser routes use
this dependency explicitly; existing bearer-only dependencies are unchanged.
Approval and role checks remain the responsibility of the account services.
"""

import base64
import hashlib
import hmac
import re
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse


async def unavailable():
    raise HTTPException(503, "browser authentication unavailable")


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def create_browser_session_transport(
    *,
    trusted_origin,
    csrf_secret,
    actor_factory,
    get_organization=unavailable,
    get_sessions=unavailable,
    rate_guard=unavailable,
    allow_local_http=False,
):
    if type(allow_local_http) is not bool:
        raise ValueError("explicit local HTTP setting required")
    if not isinstance(csrf_secret, bytes) or len(csrf_secret) < 32:
        raise ValueError("dedicated CSRF secret of at least 32 bytes required")
    if not callable(actor_factory):
        raise ValueError("trusted actor factory required")
    if not isinstance(trusted_origin, str):
        raise ValueError("trusted origin required")
    try:
        origin = urlsplit(trusted_origin)
        _port = origin.port
    except ValueError:
        raise ValueError("invalid trusted origin") from None
    local = (
        allow_local_http
        and origin.scheme == "http"
        and origin.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if (
        (origin.scheme != "https" and not local)
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or origin.path
        or origin.query
        or origin.fragment
        or not trusted_origin.isascii()
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in trusted_origin)
        or trusted_origin != f"{origin.scheme}://{origin.netloc}"
    ):
        raise ValueError("exact HTTPS origin required; local HTTP requires opt-in")
    secure = not local
    cookie_name = "__Host-account_session" if secure else "account_session_local"
    flow_name = "__Host-account_google_flow" if secure else "account_google_flow_local"

    def csrf(token, organization):
        message = f"account-browser-csrf-v1|{trusted_origin}|{organization}|{token}"
        return hmac.new(csrf_secret, message.encode("ascii"), hashlib.sha256).hexdigest()

    def browser_token(request):
        if f"{request.url.scheme}://{request.url.netloc}" != trusted_origin:
            raise HTTPException(400, "browser origin unavailable")
        if request.headers.getlist("authorization"):
            raise HTTPException(400, "ambiguous authentication transport")
        # Request.cookies collapses duplicate names. Inspect raw fields first.
        values = []
        for header in request.headers.getlist("cookie"):
            for item in header.split(";"):
                name, separator, value = item.strip().partition("=")
                if name == cookie_name and separator:
                    values.append(value)
        if len(values) != 1 or re.fullmatch(r"[A-Za-z0-9_-]{43}", values[0]) is None:
            raise HTTPException(401, "browser session required")
        token = values[0]
        decoded = base64.urlsafe_b64decode(token + "=")
        if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != token:
            raise HTTPException(401, "invalid browser session")
        return token

    async def context(
        request: Request,
        organization=Depends(get_organization),
        sessions=Depends(get_sessions),
        _guard=Depends(rate_guard),
    ):
        if not isinstance(organization, UUID) or organization.int == 0:
            raise HTTPException(503, "organization configuration unavailable")
        token = browser_token(request)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origins = request.headers.getlist("origin")
            supplied = request.headers.getlist("x-csrf-token")
            if (
                origins != [trusted_origin]
                or len(supplied) != 1
                or re.fullmatch(r"[0-9a-f]{64}", supplied[0]) is None
                or not hmac.compare_digest(supplied[0], csrf(token, organization))
            ):
                raise HTTPException(403, "CSRF validation failed")
        if not callable(getattr(sessions, "verify", None)):
            raise HTTPException(503, "session service unavailable")
        try:
            principal = await sessions.verify(token)
        except HTTPException as error:
            status = error.status_code if error.status_code in {401, 403, 503} else 401
            raise HTTPException(status, "browser session unavailable") from None
        except Exception:
            raise HTTPException(503, "browser session unavailable") from None
        try:
            subject, tenant = principal.subject, principal.tenant_id
            if not isinstance(subject, str) or not isinstance(tenant, str):
                raise ValueError("internal identity required")
            user_id, tenant_id = UUID(subject), UUID(tenant)
            if user_id.int == 0 or tenant_id != organization:
                raise ValueError("invalid account identity")
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(401, "account identity unavailable") from None
        return token, principal, user_id, tenant_id, sessions

    async def principal_dependency(value=Depends(context)):
        return value[1]

    async def get_actor(value=Depends(context)):
        return actor_factory(user_id=value[2], organization_id=value[3])

    router = APIRouter(prefix="/auth/browser", tags=["browser authentication"])

    @router.get("/csrf")
    async def csrf_token(value=Depends(context)):
        return private(JSONResponse({"csrf_token": csrf(value[0], value[3])}))

    @router.post("/logout", status_code=204)
    async def logout(value=Depends(context)):
        try:
            await value[4].revoke(value[0])
        except Exception:
            # Do not claim logout completed if server-side revocation failed.
            return private(JSONResponse({"detail": "logout unavailable"}, status_code=503))
        response = Response(status_code=204)
        for name in (cookie_name, flow_name):
            response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")
        return private(response)

    return {"router": router, "principal_dependency": principal_dependency, "get_actor": get_actor}
