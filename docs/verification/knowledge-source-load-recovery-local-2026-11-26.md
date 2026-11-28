# Recovery after an initial knowledge-source load failure

Verified locally on 26 November 2026 against parent
`18f03c38034622e97c9b989584a0fc032e77a0dd` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Evidence is from
automated dashboard components with fictional responses, not a new hosted/browser
acceptance journey or a live provider test.

## Observed blockers

The selected-agent source request previously marked the agent loaded in its
`finally` handler, even after the request failed or returned the wrong owner.
Knowledge actions then became available without a successfully loaded list. The
failure message told staff to select the agent again, which was unhelpful for a
workspace with only one agent. Refresh sources already existed, but loading had no
timeout: an unresolved initial request kept the page loading and refresh disabled.

The fix marks an agent loaded only after a successful owned source response.
Imports, answers, evaluations, source export and the all-agent overview stay
unavailable while the selected source list is unverified. Refresh sources remains
available after a failed load and performs only a new read; success establishes
readiness, while failed or wrong-owner retries leave actions disabled. Errors now
direct staff to that existing refresh control.

An initial source read has a 45-second deadline. At the deadline the request is
aborted, loading ends, an actionable error appears and refresh becomes available,
even if the old response never settles. Late old responses cannot replace the
recovered source list. Agent changes/unmount cancel the old request and clear its
timer. Refresh also discards an aborted response instead of marking it successful.
An unknown list is never labelled empty during a pending recovery; the empty-state
message appears only after a successful empty response.

The existing behavior after a confirmed save/review/removal followed by a failed
refresh is preserved: the acknowledged mutation remains visible and staff can retry
the read without repeating the write. Backend permissions, ownership, API schemas,
saved data and source-answer policies are unchanged. This is a UI recovery/readiness
fix, not evidence of an authorization bypass in the backend.

## Reproduce

1. Use a disposable local Knowledge dashboard with fictional mock responses and one
   registered agent. Make its initial `/documents/sources` request fail.
2. Confirm the page reports a load failure and does not claim an empty source list.
   Save source, answer, run checks, download knowledge and agent overview actions
   remain disabled. Refresh sources is available without switching agents.
3. Make refresh return a valid list for Document Agent. Only one additional read is
   made; the list appears, the error clears and actions become available. No import,
   review, deletion or customer message occurs.
4. Repeat with a failed refresh, then a response claiming Marketing Agent. Both
   leave actions disabled, with no foreign source rendered.
5. Hold the initial request unresolved and advance the component's test timers by
   45 seconds. Confirm its signal is aborted, the timeout error appears and refresh
   is available. Recover with a new read, then resolve the old request late: the
   recovered list remains intact. These are test timers, not a machine clock change.
6. Leave the page while loading: the request and timer are cancelled. During a
   delayed recovery, no empty-state claim is displayed; after a successful empty
   read, the normal no-sources message is shown.

## Validation

The four initial new regressions failed before implementation and passed after the
fix. A fifth case verifies the pending-retry empty state. The combined initial-load,
mutation recovery, agent switching and evaluation run passes 52 tests, including the
existing confirmed-write/failed-refresh behavior.

- Full dashboard: 1,095 tests passed across 105 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; its existing suites run in GitHub CI.
- No merge or deployment is included. Hosted verification remains dependent on
  hosting access recovery.
