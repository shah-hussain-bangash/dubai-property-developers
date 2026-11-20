from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A development project (e.g. a master-community phase or tower)."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "developer_name", "name"),)

    name: Mapped[str] = mapped_column(String(200))
    developer_name: Mapped[str] = mapped_column(String(200))
    community: Mapped[str] = mapped_column(String(120), index=True)
    city: Mapped[str] = mapped_column(String(80), default="Dubai")
    completion_status: Mapped[str] = mapped_column(String(32))
    handover_quarter: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    data_source: Mapped[str] = mapped_column(String(64))
    data_as_of: Mapped[date | None] = mapped_column(Date)


class Property(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A building or product line within a project."""

    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    property_type: Mapped[str] = mapped_column(String(32))


class PaymentPlan(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payment_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        CheckConstraint(
            "down_payment_pct + during_construction_pct + on_handover_pct + post_handover_pct = 100",
            name="percentages_sum_100",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    down_payment_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    during_construction_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    on_handover_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    post_handover_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    post_handover_months: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PropertyUnit(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "property_units"
    __table_args__ = (
        UniqueConstraint("property_id", "unit_ref"),
        Index("ix_property_units_org_avail_price", "organization_id", "availability", "price_aed"),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    payment_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("payment_plans.id", ondelete="SET NULL")
    )
    unit_ref: Mapped[str] = mapped_column(String(64))
    bedrooms: Mapped[int] = mapped_column(Integer)
    size_sqft: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # Null = price not confirmed. Agents must never fabricate a price.
    price_aed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    availability: Mapped[str] = mapped_column(String(32), default="unknown")
    data_as_of: Mapped[date | None] = mapped_column(Date)
