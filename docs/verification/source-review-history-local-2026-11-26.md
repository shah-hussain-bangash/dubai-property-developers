# Scoped source review history

Verified locally on 26 November 2026 against parent
`1c7610f90a047b9e13a79b160252e4241fd0d658` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All source data
and browser identities are fictional/development fixtures. No live provider was used.

## Change and storage

Explicit source reviews now retain an event with a unique ID, UTC timestamp,
authenticated reviewer's subject, previous/new review dates and previous/new
customer approval. The reviewer comes from the authenticated principal, never the
request body. A source update and its event commit in the same SQLite transaction;
an event-write failure rolls back the source update.

The existing private source database gains an `agent_source_reviews` table and
scoped index through the adapter's normal initialization. Existing source rows,
IDs, text, metadata and permissions are unchanged. Older reviews are not invented
or backfilled. Back up the complete SQLite source database to retain both sources
and their history. Test a writable deployment volume before rollout; no hosted
database was opened or upgraded in this task.

The authenticated read-only endpoint is
`GET /api/v1/knowledge/agents/{agent}/sources/{source_id}/reviews`. It requires
knowledge-read permission, uses the principal's organization and registered agent,
checks source ownership and returns private/no-store responses. Pages contain up
to 20 events, newest first, with an opaque UUID `next_cursor`. Pass it as
`before_event` for the next older page. Cursor lookup is scoped to that same
organization, agent and source; internal database sequence IDs are not exposed.

The saved-text preview loads history only when requested. It displays reviewer
IDs, timestamps in Dubai GST, date/approval transitions, older-page navigation and
a refresh-to-latest action. Failed refreshes clear the old page, timeouts permit
retry, and changing agent/unmounting aborts reads. Responses are validated before
display and actor text is rendered as plain text.

## Coverage boundary and retention

This records explicit review-form/API actions. Imports and re-imports do not create
review events; a re-import can change current metadata independently of the last
review event. This is not a complete mutation audit or immutable compliance log.
Source deletion atomically removes its associated review records. The confirmation
and history panel disclose this. Re-importing identical content after deletion
starts with an empty history, rather than reviving old review events. Records for
other owners of identical content remain intact. Each successful explicit review
request creates an event; retries are not deduplicated as a single review.

## Fictional local browser journey

1. Start a disposable local API/dashboard with mock providers. Prepare a two-page
   PDF from `pdf_fixture("historymarker")` for Document Agent, title Fictional
   review history PDF, date `2030-01-04`, customer approval off. Only the source
   calendar fixture is set to `2030-01-03`; the machine clock is unchanged.
2. Sign in locally, open Knowledge, select Document Agent and view the saved text.
   Load review history: No reviews recorded yet. Importing did not invent a review.
3. Record an explicitly confirmed review for `2030-01-05`, leaving customer use
   unchecked. Reopen saved text and load history. One event shows `dev-user`, a
   real UTC recording time displayed in GST, date `2030-01-04` to `2030-01-05`
   and staff-only to staff-only.
4. Record another confirmed review for `2030-01-06`, this time explicitly
   approving customer use. Reopen and load history. Two events appear newest
   first; the second transition is `2030-01-05` to `2030-01-06` and staff-only
   to approved. The prior event remains unchanged.
5. Select Marketing Agent: old source/history text clears and no sources appear.
   Sign out, stop the disposable servers and remove temporary login material.
6. Read the disposable store independently: exactly two events persist, both use
   the backend development principal `dev-user`, and source metadata differs from
   the original only in the final date and customer flag. Source text/ID remain.

The future review dates are simulated source-calendar dates, not session dates.
The reviewer shown in this local DEV run is the backend development identity,
not the portal login email. Authenticated API tests separately verify trusted
principal binding and organization/role restrictions; production identity wiring
is not claimed by this browser rehearsal.

[Captured page](assets/source-review-history-2026-11-26.jpg) and
[persisted fictional history](source-review-history-local-2026-11-26.json) retain
the visible outcome and event chain. The launcher, login material and private
fixture database remain unpublished.

## Checks

- **22 new API/storage cases pass**, within **60 focused history/renewal tests**:
  all 13 agent scopes, identical-content ownership in two organizations, viewer
  reads, writer restrictions, spoofed reviewer rejection, UTC recording, restart,
  43 reviews across pages of 20/20/3, scoped cursors, deletion/re-import, legacy
  database initialization and invalid actors.
- A forced SQLite append failure leaves source metadata/history unchanged and a
  later retry succeeds. Twelve concurrent reviews retain a complete previous/new
  state chain, with no missing events.
- **15 new dashboard cases pass**, within **24 focused history/review tests**:
  deferred loading, changes/GST display, empty history, older/latest pages,
  failed refresh, cancellation, timeout retry, plain actor text and invalid
  identity/date/cursor/flag rejection.
- Full local backend: **2,455 passed**, 156 skipped, four existing expected
  failures, 662 passing subtests and three warnings. Local database prerequisites
  and Unix-only file-mode checks account for skips; recovery/fencing expected
  failures remain recorded limitations.
- Full dashboard: **1,016 tests in 100 files passed**. Type checking, production
  compilation, Ruff, Python formatting and full application mypy pass. Lint has
  zero errors and 27 existing warnings. The existing Windows standalone symlink
  packaging warning remains; use a verified release artifact.

From the source root with the project environment:

```text
python -m pytest tests/security/test_source_review_history.py tests/security/test_saved_source_review.py -q -p no:cacheprovider --basetemp=../fresh-source-history-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-source-history-full
python -m ruff check .
python -m ruff format --check .
python -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker
```

From `apps/dashboard`, run `npm test -- --reporter=dot`, `npm run typecheck`,
`npm run lint` and `npm run build`. The focused new dashboard file is
`src/__tests__/SourceReviewHistory.test.tsx`.

No merge, deployment or live provider write is included. Hosted acceptance remains
pending while AWS access is unavailable. Review reminders and a broader immutable
audit/retention policy remain future work.
