"""Conservative English availability wording contract for local property drafts.

This checks explicit wording, not general factual accuracy or all paraphrases.
All accepted drafts still require human review.
"""

import re
import unicodedata

AVAILABILITY_WARNING = "Current availability must be confirmed with the developer."


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", text)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
    return " ".join(value.casefold().split())


def accepts_availability_wording(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = _normalized(text)
    warning = _normalized(AVAILABILITY_WARNING)
    if normalized.count(warning) != 1:
        return False
    remainder = normalized.replace(warning, "", 1)
    # A payment-plan option is a separate catalog attribute, not unit stock.
    remainder = re.sub(
        r"\b(?:a\s+)?payment\s+plans?(?:\s+options?)?\s+(?:(?:is|are)\s+)?available\b",
        "payment plan noted",
        remainder,
    )
    # Availability discussion belongs in the exact warning, never a live claim.
    if re.search(
        r"\b(?:un)?availab\w*\b|\b(?:reserved|sold)\b|\bin\s+stock\b|\bready\s+to\s+(?:book|buy|reserve)\b",
        remainder,
    ):
        return False
    # Catalog data cannot verify anything with a developer or a live service.
    return not re.search(
        r"\b(?:is|are|was|were|has|have|already)\s+(?:been\s+)?(?:confirmed|verified)\b|\b(?:confirmed|verified)\s+by\b",
        remainder,
    )
