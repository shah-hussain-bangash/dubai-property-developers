# HTML knowledge text fidelity

Verified locally on 25 November 2026 against PR #87 revision
`71266bee6122745743f0b74a4ea07eee33a7bb99` plus this change.

## Observed issue

The HTML importer joined every text fragment with an added space. Inline markup
inside a word, number or identifier therefore changed the extracted fact: a
fictional `D<span>XB</span>-<em>101</em>` became spaced text instead of `DXB-101`.
The same issue split decimal/grouped numbers, percentages, accented words and
Arabic words. Those altered excerpts could be stored and cited. The initial
18-case regression run reported eight failures and ten passing controls.

## Correction

The parser now joins actual text fragments without inventing inline separators.
Known block elements add line boundaries at their starts/ends, and table cells
add whitespace separators. Existing entity decoding and exclusions for script,
style, noscript, SVG and template content remain. Plain text, Markdown, PDF
extraction, ownership filters and answer/citation assembly are unchanged.

## Verification

All **18 new cases passed**: intact identifiers, grouped numbers, percentages,
hyphenated text, links, multilingual words, entities, paragraph/list/section/
heading boundaries, table rows/cells, five excluded-content tags, and a saved
source whose quoted answer retains the intact identifier and agent ownership.
The combined extraction/encoding/import/authenticated source-scope suite passed
**89 tests**.

The full local Python 3.14 suite reported **1,847 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the importer passed.

```text
python -m pytest tests/unit/test_knowledge_html_text_fidelity.py tests/unit/test_knowledge_text_encoding.py tests/unit/test_assigned_agent_knowledge.py tests/unit/test_international_knowledge_links.py tests/unit/test_knowledge_import_fetch_budget.py tests/security/test_assigned_source_api_isolation.py -q
python -m pytest -q
python -m mypy knowledge/ingestion/assigned_inputs.py
```

## Limits

This is plain-text extraction using HTML element boundaries, not browser layout
rendering, CSS visibility evaluation or JavaScript execution. Existing stored
sources are untouched; previously altered imports require removal/re-import
to replace their excerpts. No live website request was needed for the new
regressions. No live CRM writes, customer messages, merge or deployment occurred.
