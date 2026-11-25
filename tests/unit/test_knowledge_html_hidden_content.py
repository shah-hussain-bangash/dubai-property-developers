"""Explicitly hidden HTML must not become an agent's answer evidence."""

import pytest

from knowledge.assigned_sources import AssignedSources
from knowledge.ingestion.assigned_inputs import extract_input


@pytest.mark.parametrize(
    "attribute",
    ["hidden", "hidden=''", "hidden='hidden'", "hidden='until-found'", "HIDDEN", "hidden='false'"],
)
def test_hidden_attribute_excludes_element_text(attribute):
    html = f"<p>Fictional visible policy.</p><div {attribute}>Hidden unpublished payment.</div><p>Two visits.</p>"
    text = extract_input(html.encode(), "text/html")[0]
    assert "Fictional visible policy." in text and "Two visits." in text
    assert "Hidden unpublished payment" not in text


def test_nested_same_tag_does_not_end_hidden_section_early():
    html = (
        "<div hidden>Hidden first.<div>Hidden nested.</div>Hidden last.</div><p>Visible policy.</p>"
    )
    text = extract_input(html.encode(), "text/html")[0]
    assert text.strip() == "Visible policy."


def test_nested_different_hidden_tag_does_not_expose_outer_text():
    html = "<div hidden>Hidden first.<template>Hidden template.</template>Hidden last.</div><p>Visible policy.</p>"
    assert extract_input(html.encode(), "text/html")[0].strip() == "Visible policy."


@pytest.mark.parametrize("tag", ["input", "br"])
def test_hidden_void_element_does_not_hide_following_content(tag):
    html = f"<p>Visible first.</p><{tag} hidden><p>Visible second.</p>"
    text = extract_input(html.encode(), "text/html")[0]
    assert "Visible first." in text and "Visible second." in text


def test_unmatched_hidden_end_tag_does_not_expose_suppressed_svg():
    html = "<svg>Hidden first.</template>Hidden last.</svg><p>Visible policy.</p>"
    assert extract_input(html.encode(), "text/html")[0].strip() == "Visible policy."


@pytest.mark.parametrize("attribute", ["data-hidden='true'", "aria-hidden='true'"])
def test_other_attributes_do_not_claim_html_visibility_semantics(attribute):
    html = f"<p {attribute}>Visible supplied policy.</p>"
    assert extract_input(html.encode(), "text/html")[0].strip() == "Visible supplied policy."


def test_saved_agent_source_cannot_answer_from_hidden_page_content(tmp_path):
    pages = extract_input(
        b"<p>Fictional garden policy allows two visits.</p>"
        b"<div hidden>Unpublished payment requires ninety percent.</div>",
        "text/html",
    )
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    store.add("fictional-org", "documents", "Fictional policy", "website", pages)
    visible = store.answer("fictional-org", "documents", "garden policy")
    assert visible["text"] == "[1] Fictional garden policy allows two visits."
    assert not store.answer("fictional-org", "documents", "unpublished payment")["answered"]
    assert not store.answer("fictional-org", "email", "garden policy")["answered"]
