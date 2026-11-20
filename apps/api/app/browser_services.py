"""Build concrete browser services from explicitly supplied infrastructure.

No environment loading, client connections, migrations, secret generation, or
application mounting occurs during assembly. Real-service acceptance remains
separate. Registration is closed by default, including new Google identities.
"""

import hmac
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NoReturn
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.browser_application import install_browser_auth
from core.security.account_contracts import Dependency, PrincipalFactory, SessionFactory
from core.security.google_oauth_flows import FlowRedisClient, GoogleOAuthFlowStore
from core.security.google_oidc import GoogleOIDC
from database.repositories.account_approval_service import TransactionalAccountService
from database.repositories.account_authentication import AccountAuthentication
from database.repositories.account_registration import PendingAccountRegistration
from database.repositories.account_sessions import AccountSessions


@dataclass(frozen=True, slots=True)
class BrowserServiceConfig:
    trusted_origin: str
    organization_id: UUID
    owner_id: UUID
    google_client_id: str = field(repr=False)
    google_client_secret: str = field(repr=False)
    csrf_secret: bytes = field(repr=False)
    oauth_session_secret: str = field(repr=False)
    registration_enabled: bool = False
    allow_local_http: bool = False
    session_ttl_seconds: int = 3600
    flow_ttl_seconds: int = 600

    def __post_init__(self) -> None:
        for identifier in (self.organization_id, self.owner_id):
            if not isinstance(identifier, UUID) or identifier.int == 0:
                raise ValueError("trusted non-nil organization and owner UUIDs required")
        if type(self.registration_enabled) is not bool or type(self.allow_local_http) is not bool:
            raise ValueError("explicit boolean browser settings required")
        if type(self.session_ttl_seconds) is not int or not 60 <= self.session_ttl_seconds <= 3600:
            raise ValueError("session TTL must be 60 to 3600 seconds")
        if type(self.flow_ttl_seconds) is not int or not 60 <= self.flow_ttl_seconds <= 600:
            raise ValueError("flow TTL must be 60 to 600 seconds")
        if not isinstance(self.trusted_origin, str) or not self.trusted_origin.isascii():
            raise ValueError("trusted ASCII browser origin required")
        try:
            origin = urlsplit(self.trusted_origin)
            _port = origin.port
        except ValueError:
            raise ValueError("invalid browser origin") from None
        local = (
            self.allow_local_http
            and origin.scheme == "http"
            and origin.hostname
            in {
                "localhost",
                "127.0.0.1",
                "::1",
            }
        )
        if (
            (origin.scheme != "https" and not local)
            or not origin.hostname
            or origin.username is not None
            or origin.password is not None
            or origin.path
            or origin.query
            or origin.fragment
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in self.trusted_origin
            )
            or self.trusted_origin != f"{origin.scheme}://{origin.netloc}"
        ):
            raise ValueError("exact HTTPS origin required; local HTTP requires opt-in")
        for value in (self.google_client_id, self.google_client_secret):
            if not isinstance(value, str) or not value.strip() or len(value) > 4096:
                raise ValueError("trusted Google credentials required")
        if not isinstance(self.csrf_secret, bytes) or len(self.csrf_secret) < 32:
            raise ValueError("dedicated CSRF secret of at least 32 bytes required")
        if (
            not isinstance(self.oauth_session_secret, str)
            or len(self.oauth_session_secret.encode()) < 32
        ):
            raise ValueError("dedicated OAuth session secret of at least 32 bytes required")
        if hmac.compare_digest(self.csrf_secret, self.oauth_session_secret.encode()):
            raise ValueError("OAuth and CSRF secrets must be distinct")

    @property
    def callback_url(self) -> str:
        return self.trusted_origin + "/api/v1/auth/google/callback"


class _ExistingAccountsOnly(PendingAccountRegistration):
    async def register_password(self, organization_id: UUID, **credentials: str) -> NoReturn:
        raise HTTPException(403, "registration unavailable")

    async def _create(
        self,
        session: AsyncSession,
        organization_id: UUID,
        email: str,
        name: str,
        digest: str | None,
    ) -> NoReturn:
        # The inherited Google lookup can reuse an existing issuer/subject
        # mapping, but its absent-identity branch cannot insert a new account.
        raise HTTPException(403, "registration unavailable")


@dataclass(frozen=True, slots=True, repr=False)
class BrowserServiceBindings:
    config: BrowserServiceConfig
    provider: GoogleOIDC
    authentication: AccountAuthentication
    sessions: AccountSessions
    flow_store: GoogleOAuthFlowStore
    account_service: TransactionalAccountService
    registration: PendingAccountRegistration
    organization_dependency: Dependency
    rate_guard: Dependency

    def install(self, app: FastAPI, *, enabled: bool = False) -> bool:
        return install_browser_auth(
            app,
            enabled=enabled,
            trusted_origin=self.config.trusted_origin,
            csrf_secret=self.config.csrf_secret,
            oauth_session_secret=self.config.oauth_session_secret,
            organization_dependency=self.organization_dependency,
            provider=self.provider,
            authentication=self.authentication,
            sessions=self.sessions,
            flow_store=self.flow_store,
            account_service=self.account_service,
            rate_guard=self.rate_guard,
            allow_local_http=self.config.allow_local_http,
        )


def build_browser_service_bindings(
    config: BrowserServiceConfig,
    *,
    session_factory: SessionFactory,
    redis_client: FlowRedisClient,
    principal_factory: PrincipalFactory,
    password_hasher: Callable[[str], str],
    password_verifier: Callable[[str, str], bool],
    dummy_hash: str,
    rate_guard: Dependency,
) -> BrowserServiceBindings:
    if not isinstance(config, BrowserServiceConfig):
        raise ValueError("validated browser service configuration required")
    # Validate every injected contract before creating any service instance.
    if not all(
        callable(value)
        for value in (
            session_factory,
            principal_factory,
            password_hasher,
            password_verifier,
            rate_guard,
        )
    ):
        raise ValueError("reviewed service factories and rate guard required")
    if not isinstance(dummy_hash, str) or not 1 <= len(dummy_hash) <= 255:
        raise ValueError("dummy hash generated with the reviewed hasher required")
    if not all(callable(getattr(redis_client, name, None)) for name in ("set", "eval")):
        raise ValueError("injected async Redis client required")

    provider = GoogleOIDC(
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        redirect_uri=config.callback_url,
        allow_local_http=config.allow_local_http,
    )
    sessions = AccountSessions(
        session_factory, principal_factory=principal_factory, ttl_seconds=config.session_ttl_seconds
    )
    registration_class = (
        PendingAccountRegistration if config.registration_enabled else _ExistingAccountsOnly
    )
    registration = registration_class(session_factory, password_hasher=password_hasher)
    authentication = AccountAuthentication(
        session_factory,
        password_verifier=password_verifier,
        dummy_hash=dummy_hash,
        registration_service=registration,
        session_service=sessions,
        google_provider=provider,
    )
    flow_store = GoogleOAuthFlowStore(redis_client, ttl_seconds=config.flow_ttl_seconds)
    accounts = TransactionalAccountService(
        session_factory, owners={config.organization_id: config.owner_id}
    )

    async def organization_dependency() -> UUID:
        # Single-organization binding selected by trusted server configuration.
        # User headers and query parameters cannot select a different tenant.
        return config.organization_id

    return BrowserServiceBindings(
        config,
        provider,
        authentication,
        sessions,
        flow_store,
        accounts,
        registration,
        organization_dependency,
        rate_guard,
    )
