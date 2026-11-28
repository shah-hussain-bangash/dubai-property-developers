# Confirming knowledge source saves before clearing drafts

Verified locally on 27 November 2026 against parent
`9c19fa0688258356835f4ee9782fbb117dc19f98` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Verification uses
fictional dashboard responses; no new hosted or browser journey is claimed.

## Observed blocker and fix

The upload/link/pasted-text save handler previously treated every successful HTTP
response as proof of a saved source. For example, a 200 response with `{}` cleared
the selected file, title/text/URL, review-date and approval drafts, displayed a source
saved notice and refreshed the list despite lacking a saved-source acknowledgement.
That could lose the user's draft or misrepresent an uncertain save outcome.

The handler now checks the existing API acknowledgement before clearing anything:
its `agent_id` must match the selected agent, and `source` must contain structurally
valid saved-source metadata. Validation reuses the source-list rules for IDs,
titles, kinds, dates, safe URI metadata, character limits and numeric approval.
Only then does the existing clear-draft/success-notice/list-refresh sequence run.

Missing, foreign or malformed acknowledgements produce **The source save could not
be confirmed. Refresh sources before importing again.** Drafts and selected files
remain intact; no saved notice or automatic second import is produced. Refresh can
read authoritative current records before staff decide whether another import is
needed. An unconfirmed acknowledgement may follow a committed save; it does not
prove failure, undo a save, revoke source approval or establish retry guarantees.

Confirmed saves followed by a failed list refresh retain their existing distinct
success notice and recovery message. Actual API responses already include the
agent marker and metadata; no backend response schema or behavior changes. Four
older positive-save test mocks were corrected to include the marker and saved-source
metadata already present in the API. Existing sources, ownership, review/approval policy, evaluation files and
customer delivery permissions are unchanged.

These are acknowledgement structure checks. They are not an independent content,
request-body or durability proof; the trusted API remains responsible for saving
the requested source. Source text is absent from metadata acknowledgements.

## Reproduce

1. Use a disposable mock-provider Knowledge dashboard and select Document Agent.
   Prepare a fictional file upload, website link or pasted-text draft, including a
   title. Return HTTP success with `{}` for its source save.
2. Confirm the draft remains (including the selected file or text/URL), the error
   says the save could not be confirmed, and no Source saved notice appears. The
   handler must not automatically refresh or repeat the import.
3. Repeat with a missing/null source, wrong agent marker or malformed metadata.
   All are unconfirmed; no acknowledgement is applied as a successful save.
4. Model a save that commits but loses its acknowledgement: update the fictional
   API's source state while returning `{}`. Refresh sources manually. The saved
   record appears, the error clears and the draft remains available for staff to
   reconcile. Assert there was only one POST.
5. Return the normal owned saved-source acknowledgement. The existing success flow
   clears the draft. If only the following list read fails, retain the confirmed
   success notice and use read-only refresh without repeating the save.

## Validation

Three new component cases reproduced draft loss before the fix (file, website,
pasted text) and now pass. Seven malformed/foreign acknowledgement cases and one
uncertain-but-committed save/reconciliation case also pass: 11 new cases total.
The combined acknowledgement, mutation recovery, source-list and basic knowledge
run passes 49 tests. Tests inspect preserved controls and request counts, including
that recovery does not issue another import.

- Full dashboard: 1,142 tests passed across 108 files. Type checking and production
  compilation passed. Lint has zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
