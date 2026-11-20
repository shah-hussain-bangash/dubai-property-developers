from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class IntegrationMode(StrEnum):
    MOCK = "mock"
    LIVE = "live"
    DISABLED = "disabled"


class ApiAccessStatus(StrEnum):
    # A documented public/partner API exists and an HTTP adapter is provided (untested live).
    DOCUMENTED_API = "documented_api"
    # Interface only. Requires authorized partner/API access before implementing.
    PENDING_AUTHORIZED_ACCESS = "pending_authorized_access"
    # Provider not yet selected (e.g. telephony).
    PROVIDER_NOT_SELECTED = "provider_not_selected"


class IntegrationDescriptor(BaseModel):
    name: str
    display_name: str
    mode: IntegrationMode
    configured: bool
    api_access: ApiAccessStatus
    notes: str = ""
