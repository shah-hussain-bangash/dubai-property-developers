"""Exercise real PDF exports across supported ReportLab versions."""

import json
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
from pypdf import PdfReader

from core.prospect_reports import (
    UnsupportedReportText,
    prospect_batch_pdf,
    prospect_pdf,
    prospect_zip,
)
from schemas.prospect_research import Prospect, ResearchWorkspace

STAMP = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def profile(**changes):
    return Prospect.model_validate(
        {
            "id": "report-test-1",
            "name": "TEST - Zoë & José",
            "company": "Synthetic <b>Company</b>",
            "role": "Director",
            "country": "United Arab Emirates",
            "email": "qa@example.com",
            "source": "https://example.com/profile?one=1&two=2",
            "relevance": "Synthetic report verification only.",
            "collectedAt": "2026-11-20T12:00:00Z",
            **changes,
        }
    )


def pdf_text(reader):
    return "\n".join(page.extract_text() for page in reader.pages)


def test_individual_pdf_preserves_unicode_literal_markup_and_revision():
    reader = PdfReader(BytesIO(prospect_pdf(profile(), 7, STAMP)))
    text = pdf_text(reader)
    assert "TEST - Zoë & José" in text
    assert "Synthetic <b>Company</b>" in text
    assert "https://example.com/profile?one=1&two=2" in text
    assert "Workspace revision: 7" in text
    assert "2026-11-20 12:00:00 UTC" in text
    assert "PRIVATE - INTERNAL USE" in text
    assert reader.metadata.title == "Private prospect research report"


def test_image_markup_is_exported_as_literal_text_without_fetching(monkeypatch):
    def deny_image(*args, **kwargs):
        pytest.fail("Profile markup must not instantiate a report image")

    monkeypatch.setattr("reportlab.platypus.paraparser.ParaParser.start_img", deny_image)
    markup = '<img src="https://example.com/untrusted.png"/>'
    text = pdf_text(PdfReader(BytesIO(prospect_pdf(profile(company=markup), 1, STAMP))))
    assert markup in text


@pytest.mark.parametrize("name", ["TEST - العربية", "TEST - \u200bhidden", "TEST - 😀"])
def test_unsupported_text_is_rejected_instead_of_silently_corrupting_pdf(name):
    with pytest.raises(UnsupportedReportText, match="JSON backup"):
        prospect_pdf(profile(name=name), 1, STAMP)


def test_batch_pdf_includes_archived_profiles_and_working_bookmarks():
    profiles = [
        profile(),
        profile(id="report-test-2", name="TEST - Archived", email="", status="archived"),
    ]
    workspace = ResearchWorkspace(prospects=profiles)
    reader = PdfReader(BytesIO(prospect_batch_pdf(workspace, 9, STAMP)))
    text = pdf_text(reader)
    assert "Saved records: 2 / 500" in text
    assert "Archived: 1" in text
    assert "TEST - Archived" in text
    assert [item.title for item in reader.outline] == [
        "Batch summary",
        "1. TEST - Zoë & José",
        "2. TEST - Archived",
    ]
    destinations = [reader.get_destination_page_number(item) for item in reader.outline]
    assert destinations[0] == 0
    assert 0 < destinations[1] < destinations[2] < len(reader.pages)


def test_zip_manifest_matches_readable_pdfs_and_uses_identifiers_for_paths():
    workspace = ResearchWorkspace(prospects=[profile(name="TEST - path/name")])
    with ZipFile(BytesIO(prospect_zip(workspace, 11))) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["revision"] == 11
        assert manifest["count"] == 1
        assert manifest["private"] is True
        assert manifest["outreach_enabled"] is False
        assert set(archive.namelist()) == {*manifest["reports"], "manifest.json", "README.txt"}
        name = manifest["reports"][0]
        assert name.startswith("prospect-report-test-1-")
        assert "/" not in name
        assert "TEST - path/name" in pdf_text(PdfReader(BytesIO(archive.read(name))))


@pytest.mark.parametrize("export", [prospect_zip, prospect_batch_pdf])
def test_empty_workspace_exports_are_rejected(export):
    with pytest.raises(ValueError, match="No prospects"):
        export(ResearchWorkspace(), 1)
