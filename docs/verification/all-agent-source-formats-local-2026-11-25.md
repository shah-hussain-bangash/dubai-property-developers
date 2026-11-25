# All-agent source format journey — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `a56499f3c3957fbc0a4151ebf825838e467e8102` plus this regression coverage.
No application behavior was changed; no new blocker was observed.

## Journey and results

The authenticated API journey covers all 13 registered agents and 39 fictional
sources: one two-page PDF, one Markdown upload and one website import per agent.
It uses the real PDF subprocess and the actual website fetch/read/decode/HTML
pipeline, with DNS and HTTPS connections replaced by deterministic local fixtures.
No public website, live provider or production service is contacted.

After recreating the app against the same SQLite source store:

- All 39 sources remain assigned to their original agent.
- All 39 own-source questions return only their expected passage and source ID.
- All 13 PDF answers cite page 2; non-PDF answers have no PDF page number.
- All 468 cross-agent questions and 39 cross-organisation questions return no answer.
- All 13 hidden website-content questions return no answer.
- All 39 wrong-agent deletion attempts are rejected; legitimate removals succeed.
- Each agent's list is empty after removal, and its deleted PDF no longer answers.

Answers are labelled supplied_sources_only and sent=false. This is source-excerpt
retrieval, not fine-tuning, model training or a live outbound agent conversation.

## Reproduction

```powershell
python -m pytest tests/security/test_agent_source_format_journey.py tests/security/test_assigned_source_api_isolation.py tests/security/test_agent_knowledge_isolation.py tests/unit/test_knowledge_html_hidden_content.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check --no-cache tests/security/test_agent_source_format_journey.py
python -m ruff format --check --no-cache tests/security/test_agent_source_format_journey.py
```

The focused run passes 41 tests. The full local run passes 2,157 tests, with
155 skipped, four existing expected failures and 662 passing subtests. Ruff and
formatting pass. The new end-to-end regression is one test covering the complete
39-source lifecycle, rather than counting each assertion as a separate test.

## Limits

This verifies local authenticated API behavior. Website transport is mocked;
browser controls, scanned-PDF OCR, live network availability and production
deployment are not established by this test. The fixture verifier does not
represent a completed production identity-provider integration. No merge,
deployment, real CRM write or customer communication is performed.
