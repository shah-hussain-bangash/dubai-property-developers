"""Approved reply templates. Drafts are always reviewed before sending."""

from __future__ import annotations

from schemas.conversations.models import CustomerIntent

REPLY_TEMPLATES: dict[str, dict[CustomerIntent, str]] = {
    "en": {
        CustomerIntent.PROPERTY_ENQUIRY: (
            "Hi {name}, thank you for your interest. A licensed advisor will share options that "
            "match your requirements. Could you confirm your budget, preferred area and number "
            "of bedrooms?"
        ),
        CustomerIntent.PRICING: (
            "Hi {name}, thank you for asking. Prices change frequently, so an advisor will "
            "confirm the current price and availability with the developer before sharing it."
        ),
        CustomerIntent.PAYMENT_PLAN: "Hi {name}, here is what our documents say about the payment plan:\n{context}\nAn advisor will confirm the final terms with the developer.",
        CustomerIntent.SCHEDULE_VIEWING: (
            "Hi {name}, we'd be happy to arrange a viewing. Which days and times suit you? "
            "An advisor will confirm the appointment."
        ),
        CustomerIntent.CALLBACK_REQUEST: "Hi {name}, an advisor will call you back shortly. What time suits you best?",
        CustomerIntent.GENERAL: "Hi {name}, thank you for your message. An advisor will get back to you shortly.",
    },
    "ar": {
        CustomerIntent.GENERAL: "مرحباً {name}، شكراً لتواصلك معنا. سيتواصل معك أحد مستشارينا المرخصين قريباً.",
    },
}

ESCALATION_ACK = {
    "en": "Hi {name}, thank you for your message. A member of our team will contact you personally.",
    "ar": "مرحباً {name}، شكراً لرسالتك. سيتواصل معك أحد أعضاء فريقنا شخصياً.",
}


def render_reply(language: str, intent: CustomerIntent, name: str, context: str = "") -> str:
    table = REPLY_TEMPLATES.get(language, REPLY_TEMPLATES["en"])
    template = table.get(intent) or table.get(CustomerIntent.GENERAL) or REPLY_TEMPLATES["en"][CustomerIntent.GENERAL]
    return template.format(name=name, context=context)
