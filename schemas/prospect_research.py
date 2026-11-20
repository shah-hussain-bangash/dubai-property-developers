"""Bounded, sourced business records. Review never grants contact permission."""

import re
from datetime import datetime
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResearchTarget(StrictModel):
    audiences: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = (
        "Investors, property agents, business owners, directors"
    )
    countries: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = (
        "United Arab Emirates"
    )
    industries: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    languages: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = "English"
    dailyTarget: int = Field(default=500, ge=1, le=500)

    @field_validator("audiences", "countries", "languages")
    @classmethod
    def required(cls, value: str) -> str:
        if not value:
            raise ValueError("Required audience field")
        return value


class Prospect(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9-]{1,80}$")]
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
    company: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
    role: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
    country: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)] = ""
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] = ""
    whatsapp: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] = ""
    whatsappSource: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)] = ""
    contactResources: list[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)]
    ] = Field(default_factory=list, max_length=5)
    source: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)]
    relevance: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)]
    collectedAt: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
    status: Literal["pending", "reviewed", "archived"] = "pending"

    @field_validator("name", "company", "role", "country", "relevance")
    @classmethod
    def required(cls, value: str) -> str:
        if not value:
            raise ValueError("Required profile field")
        return value

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email format")
        return value.lower()

    @field_validator("phone", "whatsapp")
    @classmethod
    def phone_format(cls, value: str) -> str:
        if value and not re.fullmatch(r"\+[1-9]\d{6,14}", value):
            raise ValueError("International phone format required")
        return value

    @field_validator("whatsappSource")
    @classmethod
    def whatsapp_source(cls, value: str) -> str:
        return cls.public_source(value) if value else ""

    @field_validator("contactResources")
    @classmethod
    def resources(cls, values: list[str]) -> list[str]:
        return [cls.public_source(value) for value in values]

    @model_validator(mode="after")
    def whatsapp_evidence(self) -> Self:
        if self.whatsapp and not self.whatsappSource:
            raise ValueError("Recorded WhatsApp number requires a public source URL")
        return self

    @field_validator("source")
    @classmethod
    def public_source(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or "." not in url.hostname
            or url.username
            or url.password
        ):
            raise ValueError("Public HTTPS source required")
        return value

    @field_validator("collectedAt")
    @classmethod
    def timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class ResearchWorkspace(StrictModel):
    version: Literal[1] = 1
    target: ResearchTarget = Field(default_factory=ResearchTarget)
    prospects: list[Prospect] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def unique_records(self) -> Self:
        ids = set()
        names = set()
        emails = set()
        phones: set[str] = set()
        for p in self.prospects:
            name = (" ".join(p.name.lower().split()), " ".join(p.company.lower().split()))
            numbers = {v for v in [p.phone, p.whatsapp] if v}
            if (
                p.id in ids
                or name in names
                or (p.email and p.email in emails)
                or numbers.intersection(phones)
            ):
                raise ValueError("Duplicate prospect")
            ids.add(p.id)
            names.add(name)
            if p.email:
                emails.add(p.email)
            phones.update(numbers)
        return self


class WorkspaceWrite(StrictModel):
    revision: int = Field(ge=0, le=2_000_000_000)
    workspace: ResearchWorkspace
