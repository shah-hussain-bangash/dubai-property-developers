"""Prompt assembly that keeps policy and untrusted data in separate channels."""

from __future__ import annotations

from core.llm.types import ChatMessage, ChatRole
from core.policies.prompt_safety import UNTRUSTED_DATA_NOTICE, UntrustedContent

BASE_POLICY = (
    "You assist a licensed Dubai real estate brokerage. Never invent prices, availability, "
    "handover dates, or investment returns; use only facts provided in context and cite "
    "them. Never promise guaranteed ROI. If information is missing, say so and offer a "
    "human advisor."
)


def build_messages(
    *, task_instructions: str, untrusted: list[UntrustedContent], policy: str = BASE_POLICY
) -> list[ChatMessage]:
    system = f"{policy}\n\n{task_instructions}\n\n{UNTRUSTED_DATA_NOTICE}"
    data = "\n\n".join(item.render() for item in untrusted) or "(no context provided)"
    return [
        ChatMessage(role=ChatRole.SYSTEM, content=system),
        ChatMessage(role=ChatRole.USER, content=data),
    ]
