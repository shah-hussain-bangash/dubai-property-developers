"""Private prospect PDFs and a bounded ZIP, generated in memory with no delivery.

Bitstream Vera is shipped and licensed with ReportLab. Fail explicitly on missing
glyphs or bidirectional scripts rather than silently corrupting contact records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Flowable, SimpleDocTemplate

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from schemas.prospect_research import Prospect, ResearchWorkspace


class UnsupportedReportText(ValueError):
    pass


def font_name() -> str:
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    name = "ProspectVera"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont(name, str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"))
        )
    return name


def check_text(value: str, font: str) -> None:
    from reportlab.pdfbase import pdfmetrics

    chars = cast("TTFont", pdfmetrics.getFont(font)).face.charToGlyph
    for c in value:
        if c in "\n\r\t":
            continue
        if (
            ord(c) not in chars
            or unicodedata.bidirectional(c) in {"R", "AL", "RLE", "RLO", "RLI"}
            or unicodedata.category(c).startswith("C")
        ):
            raise UnsupportedReportText(
                "The PDF font cannot faithfully display this record. Download the JSON backup instead."
            )


def prospect_pdf(prospect: Prospect, revision: int, generated_at: datetime | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer

    font = font_name()
    for value in prospect.model_dump().values():
        check_text(str(value), font)
    stamp = generated_at or datetime.now(UTC)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=44,
        leftMargin=44,
        topMargin=78,
        bottomMargin=48,
        title="Private prospect research report",
        author="Dubai Real Estate AI",
        pageCompression=1,
    )
    normal = ParagraphStyle(
        "body",
        fontName=font,
        fontSize=9.5,
        leading=15,
        textColor=colors.HexColor("#223348"),
        spaceAfter=9,
        splitLongWords=True,
        alignment=TA_LEFT,
    )
    heading = ParagraphStyle(
        "heading",
        parent=normal,
        fontSize=15,
        leading=21,
        textColor=colors.HexColor("#102941"),
        spaceBefore=12,
        spaceAfter=12,
    )
    label = ParagraphStyle(
        "label",
        parent=normal,
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#52687e"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )
    story: list[Flowable] = []

    def field(title: str, value: str) -> None:
        story.append(Paragraph(escape(title.upper()), label))
        story.append(Paragraph(escape(value or "Unknown").replace("\n", "<br/>"), normal))

    story.append(Paragraph("Prospect research profile", heading))
    field("Full name", prospect.name)
    field("Company", prospect.company)
    field("Business role", prospect.role)
    field("Country", prospect.country)
    field("Public business email - unverified", prospect.email)
    field("Public business phone - unverified; WhatsApp availability unknown", prospect.phone)
    field("Reported WhatsApp number - unverified", prospect.whatsapp)
    field(
        "Recorded WhatsApp source - not proof of ownership or permission", prospect.whatsappSource
    )
    field(
        "Other recorded contact resources", "\n".join(prospect.contactResources) or "None recorded"
    )
    field(
        "Evidence of business relevance - recorded, not independently verified", prospect.relevance
    )
    field(
        "Public source URL - recorded source; contents not automatically checked", prospect.source
    )
    field(
        "Review status",
        {
            "pending": "Awaiting review",
            "reviewed": "Reviewed - not approved for outreach",
            "archived": "Archived",
        }[prospect.status],
    )
    field(
        "Contact permissions",
        "Email: unknown. WhatsApp: unknown. Calling: unknown. No outreach enabled.",
    )
    field(
        "Record information",
        f"Record ID: {prospect.id}\nRecorded at: {prospect.collectedAt}\nWorkspace revision: {revision}\nReport generated: {stamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
    )
    story.append(Spacer(1, 12))
    story.append(Paragraph("INTERNAL RESEARCH ONLY", label))
    story.append(
        Paragraph(
            "A public business profile or review status does not establish buying interest, verified contact details or permission to market. This report is a snapshot and may become outdated. Keep contact information private. No message, call or meeting was initiated.",
            normal,
        )
    )

    def page(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#102941"))
        canvas.rect(0, A4[1] - 54, A4[0], 54, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont(font, 12)
        canvas.drawString(44, A4[1] - 33, "Dubai Real Estate AI")
        canvas.setFont(font, 8)
        canvas.drawRightString(A4[0] - 44, A4[1] - 33, "PRIVATE - INTERNAL USE")
        canvas.setFillColor(colors.HexColor("#52687e"))
        canvas.setFont(font, 8)
        canvas.drawString(
            44, 27, "Prospect Research | Source-assisted record, not a verified investment lead"
        )
        canvas.drawRightString(A4[0] - 44, 27, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    data = buffer.getvalue()
    if len(data) > 1_000_000:
        raise ValueError("Report size limit exceeded")
    return data


def prospect_zip(workspace: ResearchWorkspace, revision: int) -> bytes:
    if not workspace.prospects:
        raise ValueError("No prospects to export")
    stamp = datetime.now(UTC)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        names = []
        for prospect in workspace.prospects:
            # Identifiers are validated by the schema; contact names never become paths.
            if not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", prospect.id):
                raise ValueError("Invalid report identifier")
            name = f"prospect-{prospect.id}-{(stamp + timedelta(hours=4)).strftime('%Y-%m-%d')}.pdf"
            archive.writestr(name, prospect_pdf(prospect, revision, stamp))
            names.append(name)
            if buffer.tell() > 50_000_000:
                raise ValueError("Batch size limit exceeded")
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "revision": revision,
                    "generated_at": stamp.isoformat(),
                    "batch_date_gst": (stamp + timedelta(hours=4)).strftime("%Y-%m-%d"),
                    "count": len(names),
                    "reports": names,
                    "outreach_enabled": False,
                    "private": True,
                },
                indent=2,
            ),
        )
        archive.writestr(
            "README.txt",
            "PRIVATE RESEARCH REPORTS\nOne PDF per saved prospect, including archived records.\nThis is a database snapshot, not verification or permission to contact.\nNo messages or calls were sent. Keep these reports private.\n",
        )
    return buffer.getvalue()


def prospect_batch_pdf(
    workspace: ResearchWorkspace, revision: int, generated_at: datetime | None = None
) -> bytes:
    """One private PDF snapshot, with a summary and bookmark for every saved record."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer

    if not workspace.prospects:
        raise ValueError("No prospects to export")
    if len(workspace.prospects) > 500:
        raise ValueError("Batch exceeds 500 records")
    stamp = generated_at or datetime.now(UTC)
    font = font_name()
    cover = BytesIO()
    style = ParagraphStyle(
        "summary",
        fontName=font,
        fontSize=10,
        leading=16,
        spaceAfter=12,
        textColor=colors.HexColor("#223348"),
    )
    doc = SimpleDocTemplate(
        cover,
        pagesize=A4,
        leftMargin=44,
        rightMargin=44,
        topMargin=54,
        bottomMargin=48,
        title="Private prospect research batch",
        author="Dubai Real Estate AI",
    )
    counts = {
        status: sum(p.status == status for p in workspace.prospects)
        for status in ("pending", "reviewed", "archived")
    }
    doc.build(
        [
            Paragraph("Dubai Real Estate AI - Private prospect research batch", style),
            Spacer(1, 12),
            Paragraph(
                f"Saved records: {len(workspace.prospects)} / 500<br/>Workspace revision: {revision}<br/>Batch date (Dubai): {(stamp + timedelta(hours=4)).strftime('%Y-%m-%d')}<br/>Generated: {stamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                style,
            ),
            Paragraph(
                f"Awaiting review: {counts['pending']}<br/>Reviewed: {counts['reviewed']}<br/>Archived: {counts['archived']}",
                style,
            ),
            Paragraph(
                "This PDF includes all saved records, including archived profiles. It is a database snapshot, not a completed 500-person research job. Job titles do not establish wealth, buying intent or ability to invest.",
                style,
            ),
            Paragraph(
                "Contact details and sources remain unverified. Email, WhatsApp and calling permissions are unknown. No outreach, call or meeting was initiated. Keep this report private.",
                style,
            ),
            Paragraph(
                "Each following profile keeps its source URL, evidence and saved review status. PDF bookmarks identify profiles; page numbers inside each profile restart at one.",
                style,
            ),
        ]
    )
    writer = PdfWriter()
    try:
        writer.append(PdfReader(cover), outline_item="Batch summary", import_outline=False)
        total = 0
        for index, prospect in enumerate(workspace.prospects, 1):
            data = prospect_pdf(prospect, revision, stamp)
            total += len(data)
            if total > 50_000_000:
                raise ValueError("Batch size limit exceeded")
            writer.append(
                PdfReader(BytesIO(data)),
                outline_item=f"{index}. {prospect.name}",
                import_outline=False,
            )
        writer.add_metadata(
            {"/Title": "Private prospect research batch", "/Author": "Dubai Real Estate AI"}
        )
        result = BytesIO()
        writer.write(result)
        data = result.getvalue()
        if len(data) > 50_000_000:
            raise ValueError("Batch size limit exceeded")
        return data
    finally:
        writer.close()
