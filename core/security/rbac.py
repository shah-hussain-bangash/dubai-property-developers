"""Role-based access control foundations (least privilege by default)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"
    SALES_AGENT = "sales_agent"
    MARKETING = "marketing"
    ANALYST = "analyst"
    SYSTEM = "system"  # internal automation (worker, agents)
    VIEWER = "viewer"


class Permission(StrEnum):
    LEADS_READ = "leads:read"
    LEADS_WRITE = "leads:write"
    PROPERTIES_READ = "properties:read"
    CONVERSATIONS_READ = "conversations:read"
    MESSAGES_SEND = "messages:send"
    CRM_WRITE = "crm:write"
    CALENDAR_WRITE = "calendar:write"
    AGENTS_READ = "agents:read"
    AGENTS_EXECUTE = "agents:execute"
    WORKFLOWS_READ = "workflows:read"
    WORKFLOWS_EXECUTE = "workflows:execute"
    APPROVALS_DECIDE = "approvals:decide"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    ANALYTICS_READ = "analytics:read"
    SETTINGS_ADMIN = "settings:admin"
    AUDIT_READ = "audit:read"


_READ_ONLY = {
    Permission.LEADS_READ,
    Permission.PROPERTIES_READ,
    Permission.AGENTS_READ,
    Permission.WORKFLOWS_READ,
    Permission.KNOWLEDGE_READ,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.SALES_MANAGER: frozenset(
        _READ_ONLY
        | {
            Permission.LEADS_WRITE,
            Permission.CONVERSATIONS_READ,
            Permission.MESSAGES_SEND,
            Permission.CRM_WRITE,
            Permission.CALENDAR_WRITE,
            Permission.AGENTS_EXECUTE,
            Permission.WORKFLOWS_EXECUTE,
            Permission.APPROVALS_DECIDE,
            Permission.ANALYTICS_READ,
            Permission.AUDIT_READ,
        }
    ),
    Role.SALES_AGENT: frozenset(
        _READ_ONLY
        | {
            Permission.LEADS_WRITE,
            Permission.CONVERSATIONS_READ,
            Permission.MESSAGES_SEND,
            Permission.CALENDAR_WRITE,
            Permission.AGENTS_EXECUTE,
        }
    ),
    Role.MARKETING: frozenset(_READ_ONLY | {Permission.ANALYTICS_READ}),
    Role.ANALYST: frozenset(_READ_ONLY | {Permission.ANALYTICS_READ}),
    Role.SYSTEM: frozenset(
        _READ_ONLY
        | {
            Permission.LEADS_WRITE,
            Permission.CONVERSATIONS_READ,
            Permission.CRM_WRITE,
            Permission.AGENTS_EXECUTE,
            Permission.WORKFLOWS_EXECUTE,
            Permission.ANALYTICS_READ,
            # MESSAGES_SEND / CALENDAR_WRITE intentionally absent: automation must go
            # through human approval to act on live channels.
        }
    ),
    Role.VIEWER: frozenset(_READ_ONLY),
}


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated actor (human user or internal system identity)."""

    subject: str
    tenant_id: str
    roles: frozenset[Role] = field(default_factory=frozenset)
    display_name: str | None = None

    @property
    def permissions(self) -> frozenset[Permission]:
        granted: set[Permission] = set()
        for role in self.roles:
            granted |= ROLE_PERMISSIONS.get(role, frozenset())
        return frozenset(granted)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions


SYSTEM_PRINCIPAL = Principal(
    subject="system", tenant_id="demo-org", roles=frozenset({Role.SYSTEM}), display_name="System"
)
