# Supplied source question wording

Local verification on 26 November 2026 of parent
`c5cc0f22f313105b728ce135ea357c1d3519a0cc` plus this change in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
All sources and questions are fictional. No model or website is called.

## Observed matching gap and change

“Please tell me about garden visits” failed to retrieve a source containing
“Fictional garden policy permits two visits.” Its wrapper words diluted the
overlap score. Singular/plural forms and spelling differences also missed relevant
passages, for example a payment plan question against payment plans, or installments
against instalments.

A search-only normalization module now strips a small, explicitly listed set of
leading English question wrappers and maps listed domain word forms to a common
matching term. It uses whole Unicode tokens, with no substring stemming, broad
synonym expansion, translation, generative answer or external model fallback.
For example, flat is not treated as apartment. Unlisted wording may still abstain.

The minimum-overlap and 0.5 fraction thresholds remain unchanged and operate on
the normalized term sets. Stored source text, IDs, titles, URLs, chunk/page
references and returned excerpts are unchanged. The legacy hashing tokenizer and
vector model are untouched. Existing supplied sources benefit at query time;
there is no re-ingestion, vector rebuild or schema migration.

## Regression evidence

New file: `tests/unit/test_supplied_question_wording.py`, **29 cases**.

- Before the fix: **25 failed, four passed**.
- After the fix: all **29 pass**, within **121 focused passing tests**.
- Ten natural-wording/inflection/spelling examples return the exact original quote.
- All 13 agent identities retain organization/agent, staff/customer and removal
  boundaries with the newly supported query form.
- Unsupported wording, substring fragments, accented-word fragments and filler-only
  questions abstain. The HTTP case retains the source's original instalments spelling.
- Existing Unicode, PDF/source-format lifecycle, source-bound approval, review-date
  and source API isolation tests pass. One existing Starlette TestClient/httpx
  deprecation warning remains in the focused Python 3.14 run.
- Ruff, formatting and focused mypy pass.
- Full local backend suite: **2,264 passed**, 156 skipped, four existing expected
  failures and 662 passing subtests in 70.85 seconds; three warnings remain.
  Expected failures continue to document cross-system recovery/fencing limitations.

From the source root with the project virtual environment:

```text
python -m pytest tests/unit/test_supplied_question_wording.py tests/unit/test_unicode_source_matching.py tests/unit/test_assigned_agent_knowledge.py tests/security/test_assigned_source_api_isolation.py tests/security/test_agent_source_format_journey.py tests/security/test_source_bound_approvals.py tests/security/test_source_review_deadline_preservation.py -q -p no:cacheprovider --basetemp=../fresh-wording-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-wording-full
python -m ruff check knowledge/retrieval/source_terms.py knowledge/assigned_sources.py tests/unit/test_supplied_question_wording.py
python -m ruff format --check knowledge/retrieval/source_terms.py knowledge/assigned_sources.py tests/unit/test_supplied_question_wording.py
python -m mypy knowledge/retrieval/source_terms.py knowledge/assigned_sources.py
```

## Limits

This is a focused lexical improvement. It does not establish general paraphrase
quality, factual entailment, cross-language retrieval or semantic understanding.
The search still selects matching passages; staff must review their full wording.
Customer/source ownership, approval, review-date and delivery controls remain in
place. It adds no new facts or provider permissions. No merge, deployment, live
message or CRM write is performed; hosted acceptance still awaits AWS recovery.
