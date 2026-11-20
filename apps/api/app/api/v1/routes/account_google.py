"""Google browser routes awaiting trusted application composition.

Requires Authlib session middleware, matching Google provider/authentication
configuration, a real one-use flow store, rate limits, and trusted organization
routing. The browser cookie still requires a reviewed cookie-to-API transport.
No application mounting or middleware installation occurs here.
"""

import re
import secrets
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse


async def unavailable():
    raise HTTPException(503, "Google sign-in unavailable")


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def create_google_auth_router(
    *,
    get_organization=unavailable,
    get_provider=unavailable,
    get_authentication=unavailable,
    get_flow_store=unavailable,
    rate_guard=unavailable,
    allow_local_http=False,
):
    if type(allow_local_http) is not bool:
        raise ValueError("explicit local HTTP setting required")
    router = APIRouter(
        prefix="/auth/google",
        tags=["Google authentication"],
        dependencies=[Depends(rate_guard)],
    )

    def transport(request):
        local = (
            allow_local_http
            and request.url.scheme == "http"
            and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if request.url.scheme != "https" and not local:
            raise HTTPException(400, "HTTPS required")
        return not local

    def cookie_names(secure):
        if secure:
            return "__Host-account_google_flow", "__Host-account_session"
        return "account_google_flow_local", "account_session_local"

    def organization_id(value):
        if not isinstance(value, UUID) or value.int == 0:
            raise HTTPException(503, "organization configuration unavailable")
        return value

    def failed(status, secure, detail):
        flow_cookie, _session_cookie = cookie_names(secure)
        response = JSONResponse({"detail": detail}, status_code=status)
        response.delete_cookie(
            flow_cookie,
            path="/",
            secure=secure,
            httponly=True,
            samesite="lax",
        )
        return private(response)

    @router.get("/start")
    async def start(
        request: Request,
        organization=Depends(get_organization),
        provider=Depends(get_provider),
        store=Depends(get_flow_store),
    ):
        secure = transport(request)
        organization = organization_id(organization)
        if "session" not in request.scope:
            return failed(503, secure, "Google sign-in unavailable")
        try:
            response = await provider.start(request)
            location = urlsplit(response.headers.get("location", ""))
            states = parse_qs(location.query, keep_blank_values=True).get("state", [])
            if (
                response.status_code not in {302, 303, 307}
                or location.scheme != "https"
                or location.hostname != "accounts.google.com"
                or location.username is not None
                or location.password is not None
                or location.port not in (None, 443)
                or location.fragment
                or len(states) != 1
                or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", states[0]) is None
            ):
                raise ValueError("invalid provider redirect")
            binding = secrets.token_urlsafe(32)
            await store.reserve(states[0], organization, binding)
        except Exception:
            return failed(503, secure, "Google sign-in unavailable")
        flow_cookie, _session_cookie = cookie_names(secure)
        response.set_cookie(
            flow_cookie,
            binding,
            max_age=600,
            path="/",
            secure=secure,
            httponly=True,
            samesite="lax",
        )
        return private(response)

    @router.get("/callback")
    async def callback(
        request: Request,
        organization=Depends(get_organization),
        authentication=Depends(get_authentication),
        store=Depends(get_flow_store),
    ):
        secure = transport(request)
        organization = organization_id(organization)
        flow_cookie, session_cookie = cookie_names(secure)
        states = request.query_params.getlist("state")
        codes = request.query_params.getlist("code")
        binding = request.cookies.get(flow_cookie, "")
        if (
            "session" not in request.scope
            or "error" in request.query_params
            or len(states) != 1
            or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", states[0]) is None
            or len(codes) != 1
            or not 1 <= len(codes[0]) <= 4096
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", binding) is None
        ):
            return failed(400, secure, "invalid Google sign-in flow")
        try:
            consumed = await store.consume(states[0], organization, binding)
        except Exception:
            return failed(503, secure, "Google sign-in unavailable")
        if consumed is not True:
            return failed(400, secure, "invalid Google sign-in flow")
        try:
            token = await authentication.login_google(organization, request=request)
        except HTTPException as error:
            status = error.status_code if error.status_code in {401, 403, 409, 503} else 401
            return failed(status, secure, "Google sign-in could not be completed")
        except Exception:
            return failed(401, secure, "Google sign-in could not be completed")
        if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            return failed(503, secure, "session service unavailable")
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(
            flow_cookie,
            path="/",
            secure=secure,
            httponly=True,
            samesite="lax",
        )
        response.set_cookie(
            session_cookie,
            token,
            max_age=3600,
            path="/",
            secure=secure,
            httponly=True,
            samesite="lax",
        )
        return private(response)

    return router
