# Hidden HTML knowledge content — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `6d071a9afb690886c4f781a3117b91f97fec3bb5` plus this change.
All documents, page content and agent questions are fictional. No website is fetched.

## Observed blocker

The HTML importer excluded script/style/template sections but ignored the HTML
hidden attribute on ordinary elements. An unpublished payment statement inside
a hidden div could therefore become an agent's saved source and quoted answer.
An unrelated closing hidden tag could also end the old suppression counter early.

## Change

New HTML imports suppress elements carrying the hidden attribute and their text.
Suppression ends only at the matching outer element, accounting for nested elements
of the same tag. Hidden void elements do not suppress following visible content.
Existing script, style, noscript, SVG and template exclusions remain covered.

The change preserves visible inline facts and block/table boundaries. Attributes
such as data-hidden and aria-hidden do not independently establish HTML visibility
and are not treated as the HTML hidden attribute. This is bounded HTML text
extraction, not a CSS/JavaScript renderer or a complete browser DOM implementation.

## Reproduction and outcomes

```powershell
python -m pytest tests/unit/test_knowledge_html_hidden_content.py tests/unit/test_knowledge_html_text_fidelity.py tests/unit/test_assigned_agent_knowledge.py tests/unit/test_knowledge_text_encoding.py tests/security/test_assigned_source_api_isolation.py tests/security/test_source_bound_approvals.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache knowledge/ingestion/assigned_inputs.py tests/unit/test_knowledge_html_hidden_content.py
python -m ruff format --check --no-cache knowledge/ingestion/assigned_inputs.py tests/unit/test_knowledge_html_hidden_content.py
python -m mypy --cache-dir=nul knowledge/ingestion/assigned_inputs.py
```

Before the fix, ten new cases failed and four passed. After it, all 14 pass in a
focused run of 112 tests. The saved-source case answers from visible garden policy,
cannot answer from the hidden payment statement, and does not share its source
with another agent. The suite also covers hidden attribute forms, nested elements,
void elements, mismatched end tags, Unicode text and source-bound approvals.

The full local run passes 2,156 tests, with 155 skipped, four existing expected
failures and 662 passing subtests. Ruff, formatting and the focused type check pass.

## Limits

Previously saved imports are not rewritten. Re-import and remove the older source
if it contained unwanted hidden text; the revised extraction can have a new source
ID. CSS-only hiding and dynamically rendered content are outside this parser's
scope. No merge, website deployment or customer communication is performed.
