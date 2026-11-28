# Saved source text preview

Local verification on 26 November 2026 of parent
`670cebaffe648ee4a1bf8e9f1806bd5aa319d5e3` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All fixtures are
fictional. This is local acceptance, not a hosted staging or production result.

## Change

Saved sources previously exposed only their metadata in the Knowledge page. Staff
could set review dates but could not read the saved extracted text before review.
Each source now has a View saved text action. The preview shows the stored text,
PDF page numbers and empty-page notices, with an explicit close action. It clears
when selecting another agent or beginning another knowledge operation.

The authenticated `GET /api/v1/knowledge/agents/{agent}/sources/{source_id}` endpoint
requires the existing knowledge-read permission. Its lookup binds the principal's
organization, registered agent and source ID in the same SQL query. Foreign,
missing and removed sources return the same not-found response. Responses are
private/no-store. Source text is rendered as plain text, never HTML or instructions.
The page verifies owner/source IDs, source kind, supported URI, page sequence and
stored character count, including Unicode code-point counting.

This is a saved extraction, not the original PDF, an OCR viewer or a live website.
It reads at most the existing source limits of 100 pages and 200,000 characters.
Expired and staff-only sources remain readable by authorized staff for review.
Opening a preview does not renew a deadline, approve customer use, add knowledge,
call a website/model or change retrieval eligibility. There is no original-file
download or source-editing feature in this increment.

## Local browser reproduction

1. Start a disposable local API/dashboard with mock providers and source storage.
   Prepare a two-page PDF using
   `tests.security.test_agent_source_format_journey.pdf_fixture("previewmarker")`,
   extract it with the normal PDF extractor and store it under Document Agent,
   title Fictional expired PDF, review date `2030-01-02`, customer approval off.
2. Set only the disposable source calendar fixture to `2030-01-03`. These are
   simulated dates; the machine clock and production configuration are unchanged.
3. Sign in to the local admin workspace, open Knowledge, select Document Agent
   and click View saved text: Fictional expired PDF. Both pages appear:
   `Fictional previewmarker covermarker cover page.` and
   `Fictional previewmarker pdfmarker policy allows three visits.`
   [Saved text preview](assets/saved-source-preview-2026-11-26/01-saved-pdf-text.jpg).
4. Ask `previewmarker pdfmarker`. The preview clears and the existing explicit
   no-answer response appears because the source is overdue. The stored date
   remains `2030-01-02`, customer approval remains off and there is still one source.
   [Preview preserves expiry](assets/saved-source-preview-2026-11-26/02-preview-keeps-expiry.jpg).
5. Open the preview again and select Marketing Agent. The old text clears and
   Marketing has no sources. Sign out and stop the disposable servers; remove
   temporary login material. Compare stored metadata against the prepared fixture:
   it is unchanged after all browser actions.

The browser used the local development identity. Separate authenticated API tests
exercise both organizations and the viewer role. The private source database,
calendar fixture and login launcher remain outside the published repository.

Fictional source content ID:
`b5d510c0a355379d9939627ab126289908f9676372e5606efa7a3a2bbc55511a`.

## Checks

- **53 new API cases pass**: four source formats across all 13 agents, exact saved
  metadata/text, PDF page numbering, viewer access, foreign-agent/organization
  rejection, persistence after restart, expired-source reading without retrieval
  revival, deletion, missing IDs and authentication.
- **11 new dashboard cases pass**: PDF/empty pages, read-only request, closing,
  agent switching, refresh/error recovery, plain-text markup, Unicode counts and
  rejection of mismatched owners, IDs, page numbers, URIs or character counts.
- Full local backend: **2,395 passed**, 156 skipped, four existing expected
  failures, 662 passing subtests and three warnings. Database prerequisites and
  the Unix-only file-mode check account for skips. Recovery/fencing expected
  failures remain documented limitations.
- Full dashboard: **992 tests in 98 files passed**. Type checking and production
  compilation pass. Lint has zero errors and 27 existing warnings. The existing
  Windows standalone symlink packaging warning remains; use a verified release
  artifact rather than this local standalone folder.
- Ruff, Python formatting and full application mypy pass.

From the repository root with the project environment:

```text
python -m pytest tests/security/test_saved_source_preview.py -q -p no:cacheprovider --basetemp=../fresh-source-preview-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-source-preview-full
python -m ruff check .
python -m ruff format --check .
python -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker
```

From `apps/dashboard`, run `npm test -- --reporter=dot`, `npm run typecheck`,
`npm run lint` and `npm run build`. The focused dashboard file is
`src/__tests__/SavedSourcePreview.test.tsx`.

No merge, deployment, live provider write or source schema migration is included.
Hosted acceptance still depends on restored AWS access.
