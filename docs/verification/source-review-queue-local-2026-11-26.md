# Selected-agent source review queue

Verified locally on 26 November 2026 against parent
`ec7fb45969a16951fec655e0c8ea60facf5ad335` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All sources and
browser credentials are fictional/development fixtures; no live provider was used.

## Behavior

Knowledge now includes Sources needing review for the selected agent. Check review
dates loads a server-calculated summary and the actionable sources, oldest deadline
first. Review source opens that owned source's saved text and existing review form.
After a source is added, removed or its saved metadata changes, the displayed queue
clears; check again for a fresh result. Agent switching also clears/cancels results.

The read-only authenticated endpoint is
`GET /api/v1/knowledge/agents/{agent}/review-queue`. It requires knowledge-read
permission, uses the principal's organization and registered agent, and returns
private/no-store responses. It reads source metadata only, within the existing
100-source cap. No source content, deadline, customer approval or review event is
changed by checking the queue.

The source store calculates one `as_of` server calendar day, matching the calendar
used for retrieval expiry:

| Status | Deadline relative to server day | Listed for action |
| --- | --- | --- |
| Overdue | Before today | Yes |
| Due soon | Today through seven days ahead, inclusive | Yes |
| Current | More than seven days ahead | No |
| Undated | No deadline | No; counted separately |

Today remains an eligible review day; the queue does not expire it early. Undated
sources retain their existing no-cutoff behavior. Date status does not grant
customer approval. Results show the checked date and remain a snapshot until
refreshed; the device's clock is not used to classify them.

This is a manual in-page queue, not a scheduled reminder or outbound notification.
Opening an action only reads the source. Existing explicit review confirmation,
fresh customer-approval choice and review-history transaction still govern saving.

## Fictional local browser journey

1. Start a disposable local API/dashboard with mock providers. Prepare five text
   sources for Document Agent: Fictional overdue policy (`2030-01-02`), Fictional
   review today (`2030-01-03`), Fictional review next week (`2030-01-10`), Fictional
   current policy (`2030-01-11`) and Fictional undated policy (no date). Set only
   the source-calendar fixture to `2030-01-03`. The machine clock is unchanged.
2. Sign in locally, open Knowledge, select Document Agent and click Check review
   dates. The page shows **1 overdue, 2 due soon, 1 current, 1 undated**, with three
   review actions. Today and the seventh day are both due soon.
   [Initial queue](assets/source-review-queue-2026-11-26/01-review-queue.jpg).
3. Independently read the fixture store: all five source records exactly match
   their prepared metadata and no review events exist. The check is read-only.
4. Click Review source: Fictional overdue policy. Its saved text opens. Review
   it, choose `2030-02-01`, confirm review and leave customer use unchecked. Save.
   The old queue clears with the source metadata change.
5. Check again. The page shows **0 overdue, 2 due soon, 2 current, 1 undated**.
   Only the two due-soon actions remain. Exactly five sources remain; only the
   reviewed source's deadline changed, and only that explicit save created a review
   event. [Queue after renewal](assets/source-review-queue-2026-11-26/02-queue-after-renewal.jpg).
6. Select Marketing Agent and check dates: all counts are zero and no old items
   remain. Sign out, stop the disposable servers and remove temporary login material.

Future deadlines above are simulated fixture dates, not session dates. The browser
used local DEV identity; authenticated API tests separately cover organizations
and viewer access. [Before/after metadata evidence](source-review-queue-local-2026-11-26.json)
records the source identities, counts and retained metadata. Private fixture stores,
login material and launchers remain unpublished.

## Verification

- **14 new API cases pass**: all 13 agent scopes with overdue/today/seventh-day/
  eighth-day/undated cases, organization and agent separation, restart, viewer
  read access, no metadata/history writes, explicit renewal/deletion refresh,
  empty queues, authentication and unknown agents.
- **15 new dashboard cases pass**: explicit loading, server-date display,
  queue-to-source action, empty/undated messaging, failed refresh/retry,
  cancellation on agent changes, reset on source changes, timeout retry,
  invalid owner/count/date/classification rejection and inclusive due boundaries.
- Full local backend: **2,469 passed**, 156 skipped, four existing expected
  failures, 662 passing subtests and three warnings. Local database prerequisites
  and Unix-only file-mode checks account for skips; recovery/fencing expected
  failures remain documented limitations.
- Full dashboard: **1,031 tests in 101 files passed**. Type checking, production
  compilation, Ruff, Python formatting and full application mypy pass. Lint has
  zero errors and 27 existing warnings. The existing Windows standalone symlink
  packaging warning remains; use a verified release artifact.

From the source root with the project environment:

```text
python -m pytest tests/security/test_source_review_queue.py -q -p no:cacheprovider --basetemp=../fresh-source-queue-review
python -m pytest -q -p no:cacheprovider --basetemp=../fresh-source-queue-full
python -m ruff check .
python -m ruff format --check .
python -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker
```

From `apps/dashboard`, run `npm test -- --reporter=dot`, `npm run typecheck`,
`npm run lint` and `npm run build`. The focused new dashboard file is
`src/__tests__/SourceReviewQueue.test.tsx`.

No schema migration, merge, deployment or live provider write is included. Hosted
acceptance remains pending while AWS access is unavailable. Scheduled reminders
and cross-agent review administration remain future work.
