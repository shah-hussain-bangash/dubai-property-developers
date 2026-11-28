# Bounded reads in coverage, review queue and history panels

Verified locally on 27 November 2026 against parent
`c40f874713530a5102174edbb3fb8d9741297966` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Verification uses
fictional component responses; no new hosted/browser acceptance journey is claimed.

## Observed blocker and fix

The main Knowledge runner had bounded UI waiting, but the independently loaded
source overview, review-date queue and source review history still only aborted
their signal at timeout. If a read ignored that signal and remained unresolved,
each panel stayed busy indefinitely and its retry button never became available.
Unmount also left its timer waiting for the underlying promise to settle.

These three read-only panels now use a shared abort-aware wait around their existing
GET request. The existing 45-second timer aborts the signal and ends the UI wait even
if the request does not cooperate. Each panel then shows its existing timeout error
and enables its own manual retry. Late expired results cannot replace the newer
panel state or release a newer read's busy lock. Only the active controller clears
that lock. Scope/metadata parsing and existing report-clearing behavior remain.

Unmount aborts the wait and clears its timer/listener without updating a disposed
view. Late request rejection remains handled. An already-cancelled signal does not
start a read, and a synchronous reader failure is forwarded with listener cleanup.
No new polling, writes or automatic retries are introduced.

This bounds the local UI wait; it does not forcibly stop server processing or
native transport work. These are metadata/history reads, so this fix does not alter
the main operation runner's source-refresh requirement after an uncertain mutation.
Each panel continues to use its existing agent/organization/source scope checks,
private API behavior, pagination/date window and manual loading controls. Backend
schemas, permissions, stored sources, review history and delivery policy are unchanged.

## Reproduce

1. In a disposable local mock-provider dashboard, load an agent's sources normally.
   For each panel, hold its GET promise unresolved while ignoring its abort signal:
   - Knowledge across your agents: Check all agents' sources.
   - Sources needing review: Check review dates.
   - Source review history inside a saved-text preview: Load review history.
2. Advance component test timers 45 seconds. Confirm the request signal is aborted,
   the panel displays its timeout error and the manual load/check button is enabled.
   Machine time and production configuration are unchanged.
3. Start a fresh read but keep it pending. Resolve the first expired request: it
   must not display results or unlock the fresh read. Resolve the fresh request
   with a valid empty response: the expected empty state appears and the error clears.
   All requests remain reads; none uses POST, PATCH or DELETE.
4. Unmount during each stalled panel read. Its signal is aborted and no deadline
   remains. Reject the underlying promise afterward: no disposed-view error or
   unhandled rejection is produced.
5. Existing normal loading, latest/older review pages, review-queue navigation,
   date/count validation and agent/source changes retain their previous behavior.

## Validation

The three new panel timeout/retry cases failed before the fix and now pass. Three
unmount/late-rejection cases plus already-cancelled and synchronous-failure checks
also pass: eight new cases total. Combined with existing history, queue and overview
regressions, the focused run passes 53 tests.

Tests deliberately keep the transport promises pending after abort, start a second
read, and verify both late-result exclusion and lock ownership. Cleanup tests also
check zero remaining timers and consume a deliberately late rejection.

- Full dashboard: 1,173 tests passed across 112 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
