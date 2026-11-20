"""Lead field normalization: phone (E.164), email, locations, dedupe keys."""

from __future__ import annotations

import hashlib

import phonenumbers

DEFAULT_REGION = "AE"


def normalize_phone(raw: str | None, default_region: str = DEFAULT_REGION) -> tuple[str | None, str | None]:
    """Return (E.164, region) or (None, None) when the number is not valid."""
    if not raw:
        return None, None
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None, None
    if not phonenumbers.is_valid_number(parsed):
        return None, None
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return e164, phonenumbers.region_code_for_number(parsed)


def normalize_email(raw: str | None) -> str | None:
    return raw.strip().lower() if raw else None


def normalize_location(raw: str) -> str:
    return " ".join(part.capitalize() if part.islower() else part for part in raw.strip().split())


def dedupe_keys(email: str | None, phone_e164: str | None) -> list[str]:
    """Hashed keys so duplicate detection does not require storing raw PII in indexes."""
    keys: list[str] = []
    if email:
        keys.append("email:" + hashlib.sha256(email.encode()).hexdigest()[:32])
    if phone_e164:
        keys.append("phone:" + hashlib.sha256(phone_e164.encode()).hexdigest()[:32])
    return keys
