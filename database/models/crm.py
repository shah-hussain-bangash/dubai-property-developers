from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Contact(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_org_email", "organization_id", "email"),
        Index("ix_contacts_org_phone", "organization_id", "phone_e164"),
    )

    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    preferred_language: Mapped[str | None] = mapped_column(String(8))
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    crm_external_id: Mapped[str | None] = mapped_column(String(64))


class Lead(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("organization_id", "source", "external_ref"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
        Index("ix_leads_org_status", "organization_id", "status"),
        Index("ix_leads_org_dedupe", "organization_id", "dedupe_key"),
        Index("ix_leads_org_received", "organization_id", "received_at"),
    )

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="new")
    purpose: Mapped[str] = mapped_column(String(32), default="unknown")
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone_e164: Mapped[str | None] = mapped_column(String(20))

    phone_e164: Mapped[str | None] = mapped_column(String(20))
    phone_region: Mapped[str | None] = mapped_column(String(8))
    consent_marketing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_whatsapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message: Mapped[str | None] = mapped_column(Text)

    message: Mapped[str | None] = mapped_column(Text)
    budget_min_aed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max_aed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    preferred_locations: Mapped[list[str]] = mapped_column(default=list)
    property_types: Mapped[list[str]] = mapped_column(default=list)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    timeline_months: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int | None] = mapped_column(Integer)
    qualification_category: Mapped[str | None] = mapped_column(String(32))
    score_factors: Mapped[dict[str, Any]] = mapped_column(default=dict)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    external_ref: Mapped[str | None] = mapped_column(String(120))
    crm_external_id: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str | None] = mapped_column(String(128))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Opportunity(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (Index("ix_opportunities_org_stage", "organization_id", "stage"),)

    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL")
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("property_units.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(32), default="discovery")
    expected_value_aed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    crm_external_id: Mapped[str | None] = mapped_column(String(64))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tasks and follow-ups for humans or AI agents."""

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_org_status_due", "organization_id", "status", "due_at"),)

    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE")
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    task_type: Mapped[str] = mapped_column(String(32), default="follow_up")
    status: Mapped[str] = mapped_column(String(32), default="open")
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_agent_key: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
