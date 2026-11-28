# Customer-approved knowledge preview

Verified locally on 26 November 2026 against parent
`53aec3bd685e096abf1bf91b1f8bd696b0b71547` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All source text,
PDFs and local login material are fictional/development fixtures. No live provider
was used and no customer reply was sent.

## Change and compatibility

The Knowledge question test previously exposed only staff retrieval, which includes
current staff-only sources. Preview audience now selects Staff or Customer.
Staff remains the default and keeps the legacy request/response contract. Customer
mode returns only the selected agent's current, explicitly customer-approved
sources, using the same source-search approval/expiry filter as customer tools.
No matching eligible passage produces the existing explicit no-answer response;
there is no staff-data, demo-corpus, model or web-search fallback.

The authenticated `POST /api/v1/knowledge/agents/{agent}/answer` accepts optional
`audience: "staff" | "customer"`, defaulting to staff. Invalid values are rejected.
Customer results carry `audience: "customer"`; the dashboard requires that exact
marker before displaying a customer preview. Missing or wrong audience markers are
rejected. Legacy staff results may omit the marker; customer-labelled responses
cannot be used as staff evaluation results. Existing agent/organization ownership,
knowledge-read permission, private/no-store responses, original excerpts, citations
and `sent: false` behavior remain in force.

Changing audience clears the old answer; changing agents clears it and resets to
staff mode. Controls remain disabled during a question request. Existing saved
evaluation question sets remain staff checks; this increment adds customer mode
to the manual question preview only. Customer mode requires the updated API;
deploy the matching dashboard/API revision together when release is authorized.

This is an authenticated staff-controlled preview, not a public customer chat or
delivery action. Results reflect the source state when requested and do not grant
future send permission. Existing queued-message source/consent revalidation is
unchanged. Approval of a source is still a human decision, not proof its facts are
correct. Previewing does not change source metadata, approval or review history.

## Fictional local browser journey

1. Start a disposable local API/dashboard with mock providers and source storage.
   Prepare a two-page PDF from `pdf_fixture("previewmarker")` under Document Agent,
   title Fictional approved PDF, date `2030-01-04`, customer approval true.
   Add Fictional staff-only policy with text
   `Fictional previewmarker pdfmarker policy contains staffonlymarker internal details.`
   and no customer approval. Set only the source calendar fixture to `2030-01-03`.
2. Sign in locally, open Knowledge and select Document Agent. With staff mode
   selected, ask `previewmarker pdfmarker`. The answer quotes both the staff-only
   passage and the approved PDF's Page 2 excerpt.
   [Staff preview](assets/customer-knowledge-preview-2026-11-26/01-staff-preview.jpg).
3. Select Customer. The old answer clears. Ask the same question. The result is
   labelled Customer preview and quotes only
   `Fictional previewmarker pdfmarker policy allows three visits.` from Page 2.
   No staff-only passage appears.
   [Approved customer preview](assets/customer-knowledge-preview-2026-11-26/02-approved-customer-preview.jpg).
4. Independently read the disposable store: the two source records match the
   initial fixture exactly and no review events exist. Both previews were read-only.
5. Open the approved PDF's saved text and explicitly review it with date
   `2030-01-05`, leaving customer use unchecked. Save: it becomes staff-only.
   Ask again in customer mode. The page returns the explicit no-answer response,
   despite both passages remaining eligible for staff retrieval.
   [Approval withdrawn](assets/customer-knowledge-preview-2026-11-26/03-customer-approval-withdrawn.jpg).
6. Select Marketing Agent: the answer clears, sources are empty and audience
   resets to staff. Sign out, stop the disposable servers and remove temporary
   login material. An independent store check confirms two unchanged content IDs,
   only the explicitly reviewed PDF's date/approval changed, and one review event.

The future source dates are simulated fixture days, not session dates. The browser
used a local development principal; authenticated API tests separately verify
viewer access and organization boundaries. The private fixture database and login
launcher remain unpublished. [Structured fictional evidence](customer-knowledge-preview-local-2026-11-26.json)
contains before/after responses, source references and audience markers.

## Verification

- **21 new API cases pass**: all 13 agent identities, approved versus staff-only
  retrieval, foreign-agent/organization exclusion, viewer reads, unchanged legacy
  staff responses, no preview writes, expiry across restart, default staff-only
  renewal, fresh customer approval, deletion, seven invalid audiences, authentication
  and unknown agents.
- **10 new dashboard cases pass**, within **35 focused knowledge/evaluation tests**:
  default staff payload, verified customer request/citations, audience clearing,
  agent reset, wrong-audience rejection, customer abstention and legacy staff
  evaluation protection.
- Full local backend: **2,490 passed**, 156 skipped, four existing expected
  failures, 662 passing subtests and three warnings. Local database prerequisites
  and Unix-only file-mode checks account for skips; recovery/fencing expected
  failures remain documented limitations.
- Full dashboard: **1,041 tests in 102 files passed**. Type checking, production
  compilation, Ruff, Python formatting and full application mypy pass. Lint has
  zero errors and 27 existing warnings. The existing Windows standalone symlink
  packaging warning remains; use a verified release artifact.

From the source root with the project environment:

```text
python -m pytest tests/security/test_customer_knowledge_preview.py -q -p no:cacheprovider --basetemp=../fresh-customer-preview-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-customer-preview-full
python -m ruff check .
python -m ruff format --check .
python -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker
```

From `apps/dashboard`, run `npm test -- --reporter=dot`, `npm run typecheck`,
`npm run lint` and `npm run build`. The focused new dashboard file is
`src/__tests__/CustomerKnowledgePreview.test.tsx`.

No schema migration, merge, deployment, new agent tool permission or live provider
write is included. Hosted verification remains pending while AWS access is unavailable.
