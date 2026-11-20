"""Configurable data-retention rules (enforcement job is planned, see docs/security)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.config.settings import Settings


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    conversations_days: int
    audit_logs_days: int

    @classmethod
    def from_settings(cls, settings: Settings) -> RetentionPolicy:
        return cls(
            conversations_days=settings.data_retention_days_conversations,
            audit_logs_days=settings.data_retention_days_audit_logs,
        )

    def conversation_cutoff(self, now: datetime | None = None) -> datetime:
        return (now or datetime.now(UTC)) - timedelta(days=self.conversations_days)

    def audit_cutoff(self, now: datetime | None = None) -> datetime:
        return (now or datetime.now(UTC)) - timedelta(days=self.audit_logs_days)
