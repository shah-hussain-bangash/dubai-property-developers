"""Secret and PII redaction for logs, audit payloads and error details."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
        "client_secret",
        "private_key",
        "signature",
        "database_url",
        "redis_url",
    }
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bEAA[A-Za-z0-9]{20,}"),  # Meta-style access tokens
    re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}"),  # Slack tokens
    re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?|redis)://[^\s:@/]+:[^\s@/]+@"),
)
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
# International (+ / 00 prefix) numbers and UAE local mobiles (05X XXX XXXX). Deliberately
# narrow so dates, amounts and identifiers are not mangled.
_PHONE = re.compile(r"(?<![\w+])(?:(?:\+|00)\d[\d\s\-]{7,16}\d|05\d[\s\-]?\d{3}[\s\-]?\d{4})(?!\w)")


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return f"***{digits[-3:]}" if len(digits) >= 7 else match.group(0)


def redact_text(text: str, *, mask_pii: bool = True) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    if mask_pii:
        text = _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
        text = _PHONE.sub(_mask_phone, text)
    return text


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_KEYS or any(
        marker in lowered for marker in ("password", "secret", "token", "api_key")
    )


def redact_value(value: Any, *, mask_pii: bool = True, _depth: int = 0) -> Any:
    """Recursively redact a structure. Never mutates the input."""
    if _depth > 8:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value, mask_pii=mask_pii)
    if isinstance(value, Mapping):
        return {
            k: (
                REDACTED
                if is_sensitive_key(str(k))
                else redact_value(v, mask_pii=mask_pii, _depth=_depth + 1)
            )
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [redact_value(v, mask_pii=mask_pii, _depth=_depth + 1) for v in value]
    return value
