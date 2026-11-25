"""Imported HTML must preserve factual inline text while separating block content."""

import pytest

from knowledge.assigned_sources import AssignedSources
from knowledge.ingestion.assigned_inputs import extract_input


@pytest.mark.parametrize(
    "html,expected",
    [
        ("<p>Fictional unit D<span>XB</span>-<em>101</em>.</p>", "Fictional unit DXB-101."),
        ("<p>Fictional size <span>1,</span><b>250</b> sqft.</p>", "Fictional size 1,250 sqft."),
        (
            "<p>Fictional payment <strong>20</strong>% on booking.</p>",
            "Fictional payment 20% on booking.",
        ),
        ("<p>Fictional off<em>-plan</em> guide.</p>", "Fictional off-plan guide."),
        ("<p>Fictional <a href='/rooms'>garden</a> policy.</p>", "Fictional garden policy."),
        ("<p>Fictional caf<span>é</span> in <b>د</b>بي.</p>", "Fictional café in دبي."),
        ("<p>Fictional garden &amp; room &lt;A&gt;.</p>", "Fictional garden & room <A>."),
    ],
)
def test_inline_markup_does_not_insert_characters_into_facts(html, expected):
    assert extract_input(html.encode(), "text/html")[0].strip() == expected


@pytest.mark.parametrize(
    "html,first,second",
    [
        (
            "<p>Fictional first rule.</p>Fictional second rule.",
            "Fictional first rule.",
            "Fictional second rule.",
        ),
        (
            "<section>Fictional first rule.</section><article>Fictional second rule.</article>",
            "Fictional first rule.",
            "Fictional second rule.",
        ),
        (
            "<ul><li>Fictional first rule.</li><li>Fictional second rule.</li></ul>",
            "Fictional first rule.",
            "Fictional second rule.",
        ),
        (
            "<h4>Fictional heading.</h4>Fictional paragraph.",
            "Fictional heading.",
            "Fictional paragraph.",
        ),
    ],
)
def test_block_boundaries_separate_text_instead_of_fusing_it(html, first, second):
    text = extract_input(html.encode(), "text/html")[0]
    assert first in text and second in text
    gap = text[text.index(first) + len(first) : text.index(second)]
    assert gap and gap.isspace()


def test_table_cells_and_rows_remain_readable_without_breaking_inline_values():
    html = "<table><tr><th>Fictional unit</th><th>Size</th></tr><tr><td>D<span>XB</span>-101</td><td><b>1,250</b> sqft</td></tr></table>"
    text = extract_input(html.encode(), "text/html")[0]
    assert "DXB-101" in text
    assert text.split() == ["Fictional", "unit", "Size", "DXB-101", "1,250", "sqft"]
    assert "\n" in text.strip()


@pytest.mark.parametrize("tag", ["script", "style", "noscript", "svg", "template"])
def test_hidden_sections_stay_excluded_after_inline_text_change(tag):
    html = (
        "<p>Fictional garden policy.</p><"
        + tag
        + ">Fictional hidden command</"
        + tag
        + "><p>Two visits.</p>"
    )
    text = extract_input(html.encode(), "text/html")[0]
    assert "Fictional garden policy." in text and "Two visits." in text
    assert "hidden command" not in text


def test_saved_source_quotes_the_intact_code_and_keeps_agent_ownership(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    pages = extract_input(
        b"<p>Fictional garden unit D<span>XB</span>-<em>101</em> allows two visits.</p>",
        "text/html",
    )
    saved = store.add(
        "fictional-org",
        "documents",
        "Fictional garden policy",
        "website",
        pages,
        uri="https://example.com/gardens",
    )
    answer = store.answer("fictional-org", "documents", "garden unit")
    expected = "Fictional garden unit DXB-101 allows two visits."
    assert answer["text"] == "[1] " + expected
    assert answer["sources"][0]["excerpt"] == expected
    assert answer["sources"][0]["source_id"] == saved["id"]
    assert not store.answer("fictional-org", "email", "garden unit")["answered"]
