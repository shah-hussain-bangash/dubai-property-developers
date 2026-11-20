"""Account approval policy; authentication and storage are separate.

Integration must supply identities from verified server-side authentication,
the configured owner identity, and current persisted account state.
Never take these authorization inputs directly from registration/request fields.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum


class AccountStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class AccountAccess:
    subject: str
    organization_id: str
    status: AccountStatus = AccountStatus.PENDING
    is_active: bool = True
    decided_by: str | None = None
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("subject required")
        if not isinstance(self.organization_id, str) or not self.organization_id.strip():
            raise ValueError("organization required")
        if not isinstance(self.status, AccountStatus):
            raise ValueError("invalid account status")
        if type(self.is_active) is not bool:
            raise ValueError("is_active must be boolean")


def decide_account(
    target: AccountAccess,
    *,
    actor: AccountAccess,
    configured_owner_subject: str,
    organization_is_active: bool,
    approve: bool,
) -> AccountAccess:
    """Return a new decision; caller must persist atomically and audit it.

    Persistence must compare-and-set pending status to prevent concurrent
    decisions. This pure function provides no storage or locking.
    """
    if type(approve) is not bool:
        raise ValueError("approve must be boolean")
    if (
        not isinstance(configured_owner_subject, str)
        or not configured_owner_subject.strip()
        or actor.subject != configured_owner_subject
        or actor.status is not AccountStatus.APPROVED
        or not actor.is_active
        or organization_is_active is not True
        or actor.organization_id != target.organization_id
        or actor.subject == target.subject
        or not target.is_active
    ):
        raise PermissionError("account decision not permitted")
    if target.status is not AccountStatus.PENDING:
        raise ValueError("account already decided")
    return replace(
        target,
        status=AccountStatus.APPROVED if approve else AccountStatus.REJECTED,
        decided_by=actor.subject,
        decided_at=datetime.now(UTC),
    )


def can_access_dashboard(
    account: AccountAccess,
    *,
    authenticated_subject: str,
    authenticated_organization_id: str,
    organization_is_active: bool,
) -> bool:
    """Check account access; resource queries also need ownership filters."""
    return (
        account.status is AccountStatus.APPROVED
        and account.is_active
        and organization_is_active is True
        and account.subject == authenticated_subject
        and account.organization_id == authenticated_organization_id
    )
