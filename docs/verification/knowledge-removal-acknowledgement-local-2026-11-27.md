# Confirming knowledge-source removal acknowledgements

Verified locally on 27 November 2026 against parent
`c59ad5e0ce94777f442994bbe08eeec50808dab9` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Responses and
source records in this verification are fictional dashboard fixtures; no new hosted
or browser acceptance journey is claimed.

## Observed blocker and fix

The source-removal handler previously ignored a successful response's JSON body.
HTTP success with `{ "removed": false }`, `{}` or `null` removed the entry from
local state, displayed Source removed from future answers, and refreshed the list.
That claimed a completed removal without the API's explicit acknowledgement.

The handler now requires the existing object response with boolean `removed: true`
before updating the local list or showing the removal notice. False, missing,
string-valued, array or scalar acknowledgements are rejected as unconfirmed. The
last known list is retained and the active removal confirmation closes; the page
says **The source removal could not be confirmed. Refresh sources before trying
again.** It performs no automatic second DELETE or follow-up list read on that
invalid-acknowledgement path. Staff can use the existing read-only refresh to check
the authoritative current records.

An unconfirmed acknowledgement may follow an actual committed deletion. Retaining
the old entry describes the last known list, not proof that the source still exists.
After a read shows it absent, the normal empty/remaining list appears without
inventing a confirmed removal receipt or repeating the delete. Conversely, a valid
`removed: true` keeps the existing success flow; if only the following list read
fails, the confirmed removal notice remains and the already-removed entry does not
return. Ordinary HTTP/request errors retain existing handling.

The backend already returns the required boolean marker. No API schema, source
ownership, permission, review-history retention, retrieval or delivery changes are
included. The existing confirmation still explains that removal deletes the source's
review history. There is no undo or restore behavior. The acknowledgement remains
a trusted API assertion, not an independent database/delivery audit.

## Reproduce

1. In a disposable local Knowledge dashboard, load Document Agent with one
   fictional saved text source. Click Remove and Confirm removal.
2. Respond successfully with `removed: false`, `{}` or `null`. Confirm the source
   remains visible, no removed-from-future-answers notice appears, the confirmation
   closes and the unconfirmed-removal error directs a refresh. No automatic second
   DELETE or list read occurs.
3. Also reject literal true, a string `"true"` marker and an array. Only the object
   with boolean `removed: true` satisfies the existing acknowledgement contract.
4. Model a committed deletion with a lost acknowledgement: remove the fictional
   server record while returning `{}`. The page first retains its last known list.
   Refresh sources manually: the record disappears, the error clears and there is
   still exactly one DELETE. No confirmed-removal notice is fabricated by that read.
5. Use a normal `{ "removed": true }` acknowledgement and then fail the refresh.
   Existing success/recovery behavior remains: the source is locally removed, its
   success notice stays visible, and staff can retry the read without deleting again.

## Validation

Three new component cases reproduced false removal claims before the fix and now
pass. Three additional malformed marker cases and one uncertain-but-committed
read-reconciliation case pass: seven new cases total. The combined removal,
mutation-recovery and basic knowledge run passes 20 tests, including existing valid
confirmation and confirmed-removal/failed-refresh checks.

- Full dashboard: 1,149 tests passed across 109 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing backend suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
