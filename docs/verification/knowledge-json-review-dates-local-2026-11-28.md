# Calendar-only JSON review dates for source imports

Verified locally on 28 November 2026 against parent
`17024336adbbe219893f9a31ae3ff90029995b0c` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All source text
and identities in the API fixtures are fictional; providers are mocked. No hosted
or browser acceptance journey is claimed.

## Observed blocker and change

JSON source imports used a coercing date model for `review_by`. The real local API
accepted a Unix timestamp and a midnight datetime string and stored both as a
calendar date. Raw file uploads and explicit saved-source reviews already used
stricter date inputs. That inconsistency allowed ambiguous timestamp values to set
or replace a source's answer-expiry deadline.

The nullable JSON import date now uses strict date validation, aligned with explicit
source reviews. A supplied value must be a valid `YYYY-MM-DD` calendar string or
null; timestamp numbers (seconds, milliseconds or floats), datetime strings, invalid
calendar dates, booleans, arrays and objects are rejected with HTTP 422. Invalid
format/type website requests are rejected before ingestion/fetch is called.

This intentionally tightens compatibility for JSON callers that previously supplied
epoch numbers or midnight datetimes: send a calendar date instead. The dashboard
already submits calendar dates. Raw upload query syntax and the server-day expiry
policy remain unchanged. Calendar dates in the past still use the existing business
validation; this fix does not move that separate validation ahead of every fetch.

Omitted/null dates retain their existing meaning: a new source may be undated, but
an identical re-import preserves its existing deadline, including after expiry.
Only a deliberate valid new date renews it. Sources remain eligible through their
review day and are excluded afterward. Existing stored sources and other owners'
records are not migrated, renewed or rewritten. Customer approval, source IDs,
review-history rules, role/tenant permissions and delivery behavior are unchanged.

For a dated JSON source, use this shape:

```json
{
  "kind": "text",
  "title": "Fictional calendar policy",
  "text": "Fictional calendarmarker gardens allow two visits.",
  "review_by": "2030-01-05",
  "customer_safe": true
}
```

The date above is a fictional fixture, not a suggested review interval. Strict
formatting does not prove a human reviewed a source or that its contents are correct.

## Reproduce

1. In a disposable local mock-provider API, set only the source-store test calendar
   to 2030-01-02. Import an approved fictional text source for Document Agent with
   review date 2030-01-02. The customer preview answers through that day.
2. Re-import with timestamp seconds/milliseconds, a float timestamp, midnight UTC
   datetime strings, impossible date or wrong primitive/container types. Each is
   rejected. Read after each rejection: the original source/approval/date and the
   matching foreign organization's record remain unchanged.
3. Re-import with the date omitted and then null. Both preserve the stored deadline.
4. Advance only the source-store fixture calendar to 2030-01-03 and restart the API.
   Customer retrieval abstains. Omitted/null re-imports still preserve the expired
   deadline and cannot revive it. An explicit date 2030-01-05 renews the same source
   ID and restores eligible retrieval.
5. Invalid website date formats/types never invoke the mocked website fetch. A valid
   calendar-date website import works. New text sources with dates omitted/null
   remain legitimately undated. Existing raw file-date regressions continue to pass.

[Structured local API evidence](knowledge-json-review-dates-local-2026-11-28.json)
records strict rejections, unchanged metadata, inclusive eligibility, date preservation
after restart, next-day abstention and explicit renewal. Machine time and production
configuration are unchanged; source retrieval sends no customer message.

## Validation

Two new API cases reproduced timestamp/datetime coercion before the fix and now pass.
Thirteen agent cases verify rejected inputs, unchanged own/foreign data, preserved
omitted/null deadlines, restart/expiry and explicit renewal. Website pre-fetch and
new-undated-source cases bring this to 17 new cases. The combined strict-date,
strict-approval and raw file-date run passed 83 tests.

- Full local backend: 2,561 passed, 156 skipped, four existing expected failures
  and 662 passing subtests. Disposable database integration services run in CI.
- Ruff, Python formatting and focused mypy passed. Frontend code is unchanged;
  its existing suite is verified in CI rather than repeated locally for this fix.
- Dashboard code is unchanged; its existing suite runs in GitHub CI.
- The normal Windows runner was temporarily unable to start (file-in-use error).
  Verification continued through the approved working execution mode; the failure
  did not require project-code or filesystem-permission changes.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
