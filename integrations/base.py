"""Shared integration plumbing: config, auth strategies, resilient HTTP client.

Every adapter = Protocol (contract) + Mock (local dev/tests) + optional HTTP
implementation for providers with a documented public API. HTTP adapters are
written against public documentation and are UNTESTED against live accounts.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from pydantic import BaseModel, SecretStr

from core.exceptions.errors import IntegrationError, IntegrationNotConfiguredError
from core.observability.logging import get_logger
from core.resilience.retry import RetryPolicy, retry_async
from core.security.redaction import redact_text, redact_value
from schemas.integrations.models import IntegrationMode

logger = get_logger(__name__)


class IntegrationConfig(BaseModel):
    mode: IntegrationMode = IntegrationMode.MOCK
    timeout_seconds: float = 10.0
    max_attempts: int = 3

    @property
    def is_configured(self) -> bool:
        return False

    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_attempts=self.max_attempts, timeout_seconds=self.timeout_seconds)


# --------------------------------------------------------------------------- auth
class AuthStrategy(Protocol):
    def headers(self) -> dict[str, str]: ...


class NoAuth:
    def headers(self) -> dict[str, str]:
        return {}


class ApiKeyHeaderAuth:
    def __init__(self, header_name: str, key: SecretStr) -> None:
        self._header = header_name
        self._key = key

    def headers(self) -> dict[str, str]:
        return {self._header: self._key.get_secret_value()}


class BearerTokenAuth:
    def __init__(self, token: SecretStr) -> None:
        self._token = token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}


# --------------------------------------------------------------------------- http
class _RetryableHttpError(IntegrationError):
    retryable = True


class IntegrationRequestRejected(IntegrationError):
    """4xx from upstream: retrying will not help."""

    retryable = False


class HttpIntegrationClient:
    """httpx wrapper with auth injection, retries, timeouts and redacted errors."""

    def __init__(
        self,
        *,
        integration: str,
        base_url: str,
        auth: AuthStrategy,
        retry_policy: RetryPolicy,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise IntegrationNotConfiguredError(f"{integration}: base URL not configured")
        self.integration = integration
        self._auth = auth
        self._retry = retry_policy
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=retry_policy.timeout_seconds, transport=transport
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        expect_json: bool = True,
    ) -> Any:
        headers = {
            "Accept": "application/json" if expect_json else "text/plain",
            **self._auth.headers(),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        async def _send() -> Any:
            try:
                response = await self._client.request(
                    method, path, json=json, params=params, headers=headers
                )
            except httpx.TransportError as exc:
                raise _RetryableHttpError(
                    f"{self.integration}: transport error", details={"error": type(exc).__name__}
                ) from exc
            if response.status_code == 429 or response.status_code >= 500:
                raise _RetryableHttpError(
                    f"{self.integration}: upstream {response.status_code}",
                    details={"status": response.status_code},
                )
            if response.status_code >= 400:
                raise IntegrationRequestRejected(
                    f"{self.integration}: request rejected ({response.status_code})",
                    details={
                        "status": response.status_code,
                        "body": redact_text(response.text[:500]),
                    },
                )
            if not response.content:
                return None
            return response.json() if expect_json else response.text

        logger.info(
            "integration request",
            extra={"integration": self.integration, "method": method},
        )
        try:
            return await retry_async(_send, self._retry)
        except IntegrationError as exc:
            logger.warning(
                "integration request failed",
                extra={"integration": self.integration, "details": redact_value(exc.details)},
            )
            raise

    async def aclose(self) -> None:
        await self._client.aclose()
