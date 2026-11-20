"""WhatsApp Business messaging rules enforced before any send.

* Opt-in: the contact must have WhatsApp consent recorded.
* 24-hour customer-service window: free-form text only within 24h of the
  customer's last inbound message; otherwise an approved template is required.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

SERVICE_WINDOW = timedelta(hours=24)


def is_within_service_window(last_inbound_at: datetime | None, now: datetime | None = None) -> bool:
    if last_inbound_at is None:
        return False
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - last_inbound_at <= SERVICE_WINDOW
