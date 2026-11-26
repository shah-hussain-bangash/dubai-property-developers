# Review and renew an existing source

Verified locally on 26 November 2026 against parent
`9d056e77782578c1a2f5bb31d901a60ccb6118ee` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All records are
fictional; no live CRM, messaging, email, website or model was used.

## Change

Staff previously had to re-import material to renew a saved source. The saved-text
preview now includes Record a source review. Staff read the saved extraction,
choose a next review date and confirm that they reviewed it. Customer approval
starts unchecked, even if the saved source was already customer-approved. Saving
makes the source staff-only unless the separate customer-use checkbox is explicitly
selected. Editing the new date clears both confirmations.

The authenticated `PATCH /api/v1/knowledge/agents/{agent}/sources/{source_id}/review`
requires the existing source-write permission, a strict ISO calendar date, a true
boolean review confirmation and an optional strict boolean customer approval
(default false). Missing/invalid fields, past dates, extra fields and false review
confirmation are rejected. The body is bounded and responses are private/no-store.
The transaction changes only `review_by` and `customer_safe`, scoped by trusted
organization, registered agent and source ID. Source content, title, identity,
creation time, page references and ownership remain unchanged.

The dashboard verifies the acknowledgement against the source identity, immutable
metadata and requested date/approval. Confirmed saves update the local list before
refreshing it. If that refresh fails, the page reports that the review was saved
and asks staff to refresh before retrying. A rejected save does not claim success.
Saving closes the preview; reopen it to inspect/retry a rejected review. No source
file upload, website fetch or content replacement is part of this action.

## Local browser reproduction

1. Prepare a disposable local API/dashboard with mock providers. Store a two-page
   PDF from `pdf_fixture("renewalmarker")` under Document Agent, title Fictional
   review renewal PDF, date `2030-01-02`, customer approval true. Set only the
   disposable source-calendar fixture to `2030-01-03`. These are simulated dates;
   the machine clock and production settings are unchanged.
2. Sign in to the local admin workspace, open Knowledge and select Document Agent.
   Ask `renewalmarker pdfmarker`: the overdue source returns no answer.
3. Open View saved text. Read Page 1 and Page 2. The review and customer-use
   checkboxes both start unchecked, and Save source review is disabled.
4. Choose `2030-01-04`, confirm the review and leave customer use unchecked.
   [Confirmation form](assets/saved-source-review-2026-11-26/01-review-confirmation.jpg).
   Save: the notice says the source is staff-only and the saved deadline changes.
5. Ask again: the original Page 2 excerpt returns. A direct read-only customer
   retrieval check returns zero citations. Exactly one source remains and its
   immutable metadata matches the original fixture.
   [Renewed staff source](assets/saved-source-review-2026-11-26/02-renewed-staff-only.jpg).
6. Open the saved text again. Both confirmations start unchecked again. Choose
   `2030-01-05`, confirm review and explicitly approve customer answers. Save:
   the notice and saved list show explicit customer approval. The read-only
   customer retrieval check now returns one citation, with no message sent.
   [Explicit approval](assets/saved-source-review-2026-11-26/03-explicit-customer-approval.jpg).
7. Sign out, stop the disposable servers and remove temporary login material.

The browser used the local development identity. Authenticated API tests separately
cover role and organization boundaries. Source content ID:
`c893f50729a8efb97e496c6c6cecda27a448d2dd6bd0e9ff4bdbfd28bda16099`.
The private fixture database, calendar launcher and login material are unpublished.

## Verification

- **38 new API cases pass**: 13 agents with each approval choice (26 cases),
  11 invalid review cases and authentication/body/unknown-source checks. Cases
  verify expiry before renewal, staff-only default, actual customer retrieval,
  viewer rejection, foreign-agent/organization rejection, exact metadata/text
  preservation, no duplicate source and persistence after restart.
- **Nine new dashboard cases pass**, within 27 focused preview/recovery tests:
  default approval reset, both save choices, date-change confirmation resets,
  failed-save behavior, confirmed-save/failed-refresh recovery and rejection of
  incorrect ownership, metadata, date or approval acknowledgements.
- Full local backend: **2,433 passed**, 156 skipped, four existing expected
  failures, 662 passing subtests and three warnings. Database prerequisites and
  Unix-only file-mode checks account for local skips; recovery/fencing expected
  failures remain recorded limitations.
- Full dashboard: **1,001 tests in 99 files passed**. Type checking, production
  compilation, Ruff, Python formatting and full application mypy pass. Lint has
  zero errors and 27 existing warnings. The existing Windows standalone symlink
  packaging warning remains; use a verified release artifact.

From the source root with the project environment:

```text
python -m pytest tests/security/test_saved_source_review.py -q -p no:cacheprovider --basetemp=../fresh-saved-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-saved-review-full
python -m ruff check .
python -m ruff format --check .
python -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker
```

From `apps/dashboard`, run `npm test -- --reporter=dot`, `npm run typecheck`,
`npm run lint` and `npm run build`. The focused new dashboard file is
`src/__tests__/SourceReviewForm.test.tsx`.

Review confirmation is a staff declaration, not automatic fact verification.
This updates current metadata; it does not add a historical review log or reminders.
Current source approval/deadlines still govern queued-message source revalidation.
No source schema migration, merge, deployment or live provider write is included.
Hosted verification remains pending while AWS access is unavailable.
