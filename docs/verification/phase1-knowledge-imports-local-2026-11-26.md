# Phase 1 knowledge import review

Local verification on 26 November 2026 of parent
`b33018ca6a42ede8724b61b85d40fb23c0c8541c` plus this change in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
All files are fictional and website connections are mocked; no remote page is fetched.

## Confirmed blocker and fix

Python's HTTPResponse.read1 can return EOF with a positive remaining Content-Length
without raising IncompleteRead. The importer previously accepted that EOF, extracted
the partial body and saved it as source knowledge. A synthetic response declaring
900 bytes but containing only a readable policy sentence reproduced the issue in
both plain text and HTML, including the authenticated source API.

At EOF, website imports now reject a response whose HTTP framing still promises
more bytes. This happens before extraction and source persistence. The API returns
a bounded validation error; no new source exists and the partial policy cannot
answer a question. Connection cleanup remains in the existing finally block.

Complete Content-Length responses, complete chunked responses and valid
connection-close responses remain supported. Truncated chunked bodies continue
to fail through the existing HTTP error handler. The check does not infer missing
content when the server declares no length, or prove that a complete response
contains every fact expected by a person. Existing saved sources are not rewritten.

## Review scope

- Source file/page byte limits and PDF subprocess lifetime/resource boundaries.
- Strict Unicode text decoding, inline HTML text fidelity and hidden-content exclusion.
- Public-address checks, pinned connections, original-host TLS verification,
  international request paths and redirect revalidation.
- Shared elapsed website fetch budget, source capacity and review-date controls.
- Failed-import persistence boundaries and all-agent source-format lifecycle tests.

No further confirmed blocker was found within this review group. PDFs still need
readable text; scanned images require OCR separately. HTML extraction does not
render CSS/JavaScript. Fetch deadline checks surround blocking calls and do not
forcibly cancel blocked DNS/socket operations. This is not a live network or load test.

## Regression evidence

New test file: `tests/unit/test_knowledge_truncated_websites.py`.

- Before the fix: **four failed, four passed**.
- After the fix: all **eight new cases pass** within **124 focused passing tests**.
- New cases use the real standard-library HTTPResponse parser over an in-memory
  byte stream, not a hand-written response length counter. They cover premature
  EOF, API rejection without saving/answering, complete framing and truncated chunks.
- An existing generic response mock now explicitly sets length=None to model
  a valid response without a declared body length.
- Ruff checks, formatting and focused mypy pass.
- Full backend suite: **2,208 passed**, 155 skipped, four existing expected
  failures and 662 passing subtests in 39.35 seconds; three warnings remain.
  Expected failures document existing cross-system recovery/fencing limitations.

From the source root with the project virtual environment:

```text
python -m pytest tests/unit/test_knowledge_truncated_websites.py tests/unit/test_assigned_agent_knowledge.py tests/unit/test_knowledge_text_encoding.py tests/unit/test_knowledge_html_text_fidelity.py tests/unit/test_knowledge_html_hidden_content.py tests/unit/test_knowledge_import_fetch_budget.py tests/unit/test_international_knowledge_links.py tests/security/test_assigned_source_api_isolation.py tests/security/test_agent_source_format_journey.py tests/security/test_source_review_deadline_preservation.py -q -p no:cacheprovider --basetemp=../fresh-import-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-full-import-review
python -m ruff check knowledge/ingestion/assigned_inputs.py tests/unit/test_knowledge_truncated_websites.py tests/unit/test_assigned_agent_knowledge.py
python -m ruff format --check knowledge/ingestion/assigned_inputs.py tests/unit/test_knowledge_truncated_websites.py tests/unit/test_assigned_agent_knowledge.py
python -m mypy knowledge/ingestion/assigned_inputs.py
```

The local runs use Python 3.14 and disposable directories. The focused run emits
one existing Starlette TestClient/httpx deprecation warning.

No merge, deployment, customer communication or live CRM write is performed.
Dashboard and deployment/data compatibility review remain pending; this record
does not approve the complete PR or establish the hosted revision.
