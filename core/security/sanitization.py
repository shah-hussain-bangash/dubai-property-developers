"""Input sanitization helpers for untrusted text (customer messages, form fields)."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")
_WHITESPACE = re.compile(r"[ \t]+")


def sanitize_text(value: str, *, max_length: int = 4000) -> str:
    """Normalize unicode, strip control / bidi / zero-width characters, cap length."""
    text = unicodedata.normalize("NFKC", value)
    text = _CONTROL.sub("", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:max_length]


def sanitize_name(value: str, *, max_length: int = 120) -> str:
    text = sanitize_text(value, max_length=max_length)
    return re.sub(r"[<>{}\[\]`$\\]", "", text)
