"""Approved email templates (``string.Template`` - no code execution in templates)."""

from __future__ import annotations

from string import Template

from core.exceptions.errors import NotFoundError

TEMPLATES: dict[str, tuple[str, str]] = {
    "lead_acknowledgement": (
        "Thank you for your enquiry, $first_name",
        "Dear $first_name,\n\nThank you for contacting us about properties in Dubai. "
        "A licensed advisor will review your requirements and contact you shortly.\n\n"
        "Kind regards,\n$advisor_name",
    ),
    "follow_up_generic": (
        "Following up on your property enquiry",
        "Dear $first_name,\n\nI wanted to follow up on your recent enquiry. "
        "Would you like to schedule a call to discuss suitable options?\n\n"
        "Kind regards,\n$advisor_name",
    ),
}


def render_template(name: str, values: dict[str, str]) -> tuple[str, str]:
    try:
        subject, body = TEMPLATES[name]
    except KeyError as exc:
        raise NotFoundError(f"email template {name} not found") from exc
    return Template(subject).safe_substitute(values), Template(body).safe_substitute(values)
