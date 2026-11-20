"""Platform exception hierarchy.

Every error carries a stable machine-readable ``code`` and an HTTP status hint so
API handlers can render structured responses without leaking internals.
"""

from __future__ import annotations

from typing import Any


class PlatformError(Exception):
    code: str = "platform_error"
    status_code: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigurationError(PlatformError):
    code = "configuration_error"


class DomainValidationError(PlatformError):
    code = "validation_error"
    status_code = 422


class NotFoundError(PlatformError):
    code = "not_found"
    status_code = 404


class ConflictError(PlatformError):
    code = "conflict"
    status_code = 409


class AuthenticationError(PlatformError):
    code = "authentication_required"
    status_code = 401


class AuthorizationError(PlatformError):
    code = "forbidden"
    status_code = 403


class PolicyViolationError(PlatformError):
    code = "policy_violation"
    status_code = 403


class ApprovalRequiredError(PlatformError):
    """Raised when an action cannot proceed until a human approves it."""

    code = "approval_required"
    status_code = 202

    def __init__(self, message: str, *, approval_id: str, details: dict[str, Any] | None = None):
        super().__init__(message, details={"approval_id": approval_id, **(details or {})})
        self.approval_id = approval_id


class ToolPermissionError(AuthorizationError):
    code = "tool_permission_denied"


class AgentError(PlatformError):
    code = "agent_error"


class AgentTimeoutError(AgentError):
    code = "agent_timeout"
    status_code = 504
    retryable = True


class AgentNotFoundError(NotFoundError):
    code = "agent_not_found"


class WorkflowError(PlatformError):
    code = "workflow_error"


class IntegrationError(PlatformError):
    code = "integration_error"
    status_code = 502
    retryable = True


class IntegrationNotConfiguredError(IntegrationError):
    code = "integration_not_configured"
    status_code = 503
    retryable = False


class RateLimitExceededError(PlatformError):
    code = "rate_limited"
    status_code = 429
    retryable = True


class WebhookVerificationError(AuthenticationError):
    code = "webhook_verification_failed"
