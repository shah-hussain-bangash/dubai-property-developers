"""Deterministic keyword intent detection (English + basic Arabic).

A transparent baseline shared by supervisor, sales and channel agents. Swap for
an LLM/classifier later behind the same function signature.
"""

from __future__ import annotations

import re

from schemas.conversations.models import CustomerIntent

_RULES: tuple[tuple[CustomerIntent, tuple[str, ...]], ...] = (
    (CustomerIntent.UNSUBSCRIBE, ("unsubscribe", "stop messaging", "stop sending", "remove me", "opt out", "إلغاء الاشتراك")),
    (CustomerIntent.COMPLAINT, ("complaint", "complain", "unhappy", "disappointed", "refund", "شكوى")),
    (CustomerIntent.SCHEDULE_VIEWING, ("viewing", "visit", "see the unit", "show home", "appointment", "معاينة", "زيارة")),
    (CustomerIntent.CALLBACK_REQUEST, ("call me", "callback", "call back", "phone me", "اتصل")),
    (CustomerIntent.PAYMENT_PLAN, ("payment plan", "installment", "instalment", "post handover", "down payment", "خطة الدفع", "أقساط")),
    (CustomerIntent.PRICING, ("price", "cost", "how much", "aed", "budget", "سعر", "كم")),
    (CustomerIntent.PROPERTY_ENQUIRY, ("apartment", "villa", "townhouse", "penthouse", "bedroom", "project", "off-plan", "off plan", "شقة", "فيلا")),
)

_ARABIC = re.compile(r"[؀-ۿ]")


def detect_intent(text: str) -> CustomerIntent:
    lowered = text.lower()
    for intent, keywords in _RULES:
        if any(k in lowered for k in keywords):
            return intent
    return CustomerIntent.GENERAL if lowered.strip() else CustomerIntent.UNKNOWN


def detect_language(text: str) -> str:
    return "ar" if _ARABIC.search(text) else "en"
