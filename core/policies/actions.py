"""Classification of actions by risk, and the policy deciding which need approval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.config.settings import Settings


class ActionCategory(StrEnum):
    READ = "read"
    INTERNAL_WRITE = "internal_write"  # platform-owned state only
    CRM_WRITE = "crm_write"
    OUTBOUND_MESSAGE = "outbound_message"  # WhatsApp, email, SMS, Slack to customers
    CALENDAR_WRITE = "calendar_write"
    EXTERNAL_WRITE = "external_write"  # any other live third-party mutation


SIDE_EFFECT_CATEGORIES = frozenset(
    {
        ActionCategory.CRM_WRITE,
        ActionCategory.OUTBOUND_MESSAGE,
        ActionCategory.CALENDAR_WRITE,
        ActionCategory.EXTERNAL_WRITE,
    }
)


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """Decides whether an action category requires human approval.

    Defaults are conservative: anything reaching a customer or a calendar requires
    approval; generic external writes always do.
    """

    outbound_messages: bool = True
    crm_writes: bool = False
    calendar_events: bool = True
    external_writes: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> ApprovalPolicy:
        return cls(
            outbound_messages=settings.approval_required_for_outbound_messages,
            crm_writes=settings.approval_required_for_crm_writes,
            calendar_events=settings.approval_required_for_calendar_events,
        )

    def requires_approval(self, category: ActionCategory) -> bool:
        return {
            ActionCategory.READ: False,
            ActionCategory.INTERNAL_WRITE: False,
            ActionCategory.CRM_WRITE: self.crm_writes,
            ActionCategory.OUTBOUND_MESSAGE: self.outbound_messages,
            ActionCategory.CALENDAR_WRITE: self.calendar_events,
            ActionCategory.EXTERNAL_WRITE: self.external_writes,
        }[category]
