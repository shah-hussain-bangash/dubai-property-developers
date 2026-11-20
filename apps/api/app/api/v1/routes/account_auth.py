"""Unconfigured email/password auth router; application mounting is separate.

A trusted composition layer must inject a real rate-limit dependency,
server-selected organization UUID, and authentication service. Bearer tokens
are returned for an authenticated API transport; browser session storage and
Google OAuth browser routes are not installed by this module.
"""
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StrictStr

class PrivateValidationRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                # Default validation details can echo credential input.
                raise HTTPException(422, "invalid authentication request") from None
        return handler

class RegistrationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    full_name: StrictStr = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=12, max_length=1024)

class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)

class PendingAccountView(BaseModel):
    account_id: UUID
    organization_id: UUID
    full_name: str
    approval_status: Literal["pending"]

class SessionTokenView(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"

async def unavailable():
    raise HTTPException(503, "authentication service unavailable")

def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

def trusted_organization(value):
    if not isinstance(value, UUID) or value.int == 0:
        raise HTTPException(503, "organization configuration unavailable")
    return value

def create_account_auth_router(
    *, get_organization=unavailable, get_service=unavailable,
    rate_guard=unavailable,
):
    router = APIRouter(
        prefix="/auth", tags=["account authentication"],
        route_class=PrivateValidationRoute,
        dependencies=[Depends(rate_guard)],
    )

    @router.post("/register", status_code=201, response_model=PendingAccountView)
    async def register(
        body: RegistrationBody, response: Response,
        organization=Depends(get_organization), service=Depends(get_service),
    ):
        organization = trusted_organization(organization)
        try:
            result = await service.register_password(
                organization, email=str(body.email),
                full_name=body.full_name,
                password=body.password.get_secret_value(),
            )
        except ValueError:
            raise HTTPException(422, "invalid registration details") from None
        view = PendingAccountView.model_validate(result)
        if view.organization_id != organization:
            raise HTTPException(503, "account service inconsistency")
        private_response(response)
        return view

    @router.post("/login", response_model=SessionTokenView)
    async def login(
        body: LoginBody, response: Response,
        organization=Depends(get_organization), service=Depends(get_service),
    ):
        organization = trusted_organization(organization)
        token = await service.login_password(
            organization, email=str(body.email),
            password=body.password.get_secret_value(),
        )
        if (
            not isinstance(token, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None
        ):
            raise HTTPException(503, "session service inconsistency")
        private_response(response)
        return SessionTokenView(access_token=token)

    @router.post("/logout", status_code=204)
    async def logout(
        request: Request, response: Response,
        service=Depends(get_service),
    ):
        headers = request.headers.getlist("authorization")
        if len(headers) != 1:
            raise HTTPException(401, "bearer session required")
        parts = headers[0].split()
        if (
            len(parts) != 2 or parts[0].lower() != "bearer"
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", parts[1]) is None
        ):
            raise HTTPException(401, "bearer session required")
        await service.logout(parts[1])
        private_response(response)
        response.status_code = 204
        return response

    return router
