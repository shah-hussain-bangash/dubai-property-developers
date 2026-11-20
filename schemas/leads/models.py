"""Lead domain schemas (API, agents and workflows share these)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from core.security.sanitization import sanitize_name, sanitize_text
from schemas.properties.models import PropertyType


class LeadSource(StrEnum):
    WEBSITE = "website"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    BAYUT = "bayut"
    PROPERTY_FINDER = "propertyfinder"
    REFERRAL = "referral"
    PHONE = "phone"
    WALK_IN = "walk_in"
    OTHER = "other"


class LeadPurpose(StrEnum):
    END_USE = "end_use"
    INVESTMENT = "investment"
    RENT = "rent"
    UNKNOWN = "unknown"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    NURTURING = "nurturing"
    DISQUALIFIED = "disqualified"
    CONVERTED = "converted"
    DUPLICATE = "duplicate"


class QualificationCategory(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    NURTURE = "nurture"
    DISQUALIFIED = "disqualified"


class LeadSubmission(BaseModel):
    """Raw inbound lead as received from a form, portal or channel."""

    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    source: LeadSource = LeadSource.WEBSITE
    message: str | None = Field(default=None, max_length=4000)
    budget_min_aed: Decimal | None = Field(default=None, ge=0)
    budget_max_aed: Decimal | None = Field(default=None, ge=0)
    preferred_locations: list[str] = Field(default_factory=list, max_length=10)
    property_types: list[PropertyType] = Field(default_factory=list)
    bedrooms: int | None = Field(default=None, ge=0, le=10)
    purpose: LeadPurpose = LeadPurpose.UNKNOWN
    timeline_months: int | None = Field(default=None, ge=0, le=120)
    consent_marketing: bool = False
    consent_whatsapp: bool = False
    external_ref: str | None = Field(default=None, max_length=120)

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = sanitize_name(value)
        if not cleaned:
            raise ValueError("full_name is empty after sanitization")
        return cleaned

    @field_validator("message")
    @classmethod
    def _clean_message(cls, value: str | None) -> str | None:
        return sanitize_text(value) if value else value

    @field_validator("preferred_locations")
    @classmethod
    def _clean_locations(cls, value: list[str]) -> list[str]:
        return [sanitize_name(v, max_length=80) for v in value if v.strip()]

    @model_validator(mode="after")
    def _check_contact_and_budget(self) -> LeadSubmission:
        if not self.email and not self.phone:
            raise ValueError("at least one of email or phone is required")
        if (
            self.budget_min_aed is not None
            and self.budget_max_aed is not None
            and self.budget_min_aed > self.budget_max_aed
        ):
            raise ValueError("budget_min_aed cannot exceed budget_max_aed")
        return self


class NormalizedLead(BaseModel):
    lead_id: str
    tenant_id: str
    full_name: str
    email: str | None = None
    phone_e164: str | None = None
    phone_region: str | None = None
    source: LeadSource
    message: str | None = None
    budget_min_aed: Decimal | None = None
    budget_max_aed: Decimal | None = None
    preferred_locations: list[str] = Field(default_factory=list)
    property_types: list[PropertyType] = Field(default_factory=list)
    bedrooms: int | None = None
    purpose: LeadPurpose = LeadPurpose.UNKNOWN
    timeline_months: int | None = None
    consent_marketing: bool = False
    consent_whatsapp: bool = False
    external_ref: str | None = None
    dedupe_keys: list[str] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: LeadStatus = LeadStatus.NEW


class ScoreFactor(BaseModel):
    name: str
    points: int
    reason: str


class LeadScore(BaseModel):
    score: int = Field(ge=0, le=100)
    category: QualificationCategory
    factors: list[ScoreFactor]
    model_version: str = "rules-v1"


class LeadRouting(BaseModel):
    queue: str
    priority: str  # "p1" | "p2" | "p3"
    reason: str
    assigned_to: str | None = None
