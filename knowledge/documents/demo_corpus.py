"""Fictional knowledge corpus for demos/tests. Not real company material."""

from __future__ import annotations

from datetime import date

from knowledge.documents.models import AccessLevel, SourceDocument


def demo_documents(tenant_id: str) -> list[SourceDocument]:
    return [
        SourceDocument(
            tenant_id=tenant_id,
            document_key="faq-buying-process",
            title="Demo FAQ: Buying Process (Fictional)",
            access_level=AccessLevel.PUBLIC,
            review_by=date(2030, 1, 1),
            text=(
                "Buying process overview. Buyers usually reserve a unit with a booking form and "
                "deposit, then sign the sales agreement. Off-plan purchases are registered with "
                "the relevant authority. A licensed advisor will confirm current fees and steps.\n\n"
                "Viewings. Viewings can be scheduled with an advisor. Show homes are available "
                "for some demo projects."
            ),
        ),
        SourceDocument(
            tenant_id=tenant_id,
            document_key="demo-creek-heights-payment-plan",
            title="Demo Creek Heights Payment Plan (Fictional)",
            access_level=AccessLevel.PUBLIC,
            review_by=date(2030, 1, 1),
            text=(
                "Demo Creek Heights payment plan. 10 percent down payment, 40 percent during "
                "construction, 10 percent on handover and 40 percent post handover over 36 "
                "months. Payment plan terms must be confirmed with the developer before quoting."
            ),
        ),
        SourceDocument(
            tenant_id=tenant_id,
            document_key="internal-commission-policy",
            title="Internal Commission Policy (Fictional)",
            access_level=AccessLevel.RESTRICTED,
            allowed_roles=["sales_manager", "admin"],
            text="Commission splits are confidential and are never shared with customers.",
        ),
    ]
