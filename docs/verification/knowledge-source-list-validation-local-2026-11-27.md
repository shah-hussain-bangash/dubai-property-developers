# Safe source-list application and recovery

Verified locally on 27 November 2026 against parent
`e137dc28e1d990f09b1a4fa246ac5e1905f9762f` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Examples are
fictional dashboard responses; no new hosted or browser journey is claimed.

## Observed blocker

The workspace index and answer/preview responses had validation, but source lists
were applied after checking only the agent ID. An HTTP-success response with
`sources: null`, an object instead of an array, or a null row could enter state and
crash rendering at list-length/map/metadata access. The same problem affected a
refresh after a confirmed save, hiding its success and recovery controls.

Both the initial source read and manual/post-mutation refresh now validate the
complete list before calling the state setter or marking the selected agent ready.
A malformed initial list becomes a retryable load failure with knowledge actions
still disabled. A malformed later refresh leaves the last valid list intact and
shows an error. When a source save was already acknowledged, its success notice
and cleared draft remain; refresh can retry the read without repeating the import.
Existing review/removal acknowledgement behavior is retained.

The parser verifies the selected-agent marker, an array of up to 100 sources,
unique path-safe IDs, nonblank bounded titles, supported kinds, existing safe URI
rules, integer character counts (1-200,000 per source and two million per list),
readable creation dates, canonical calendar review dates or null, and numeric 0/1
customer approval. IDs use the same 1-100 letter/digit/underscore/hyphen-safe contract
as the workspace registry; actual backend source IDs are 64-character hex strings.
All fields are checked before any list is applied; valid metadata, Unicode and URI
spelling are preserved. Empty owned lists remain supported.

These are structural checks, not independent proof of source content, ownership or
approval correctness. The API remains responsible for trusted organization/agent
ownership and saved content. No backend schema, permission, retrieval, approval,
review-history or delivery behavior changes. The parser does not compare the
metadata's character count against text that is absent from list responses; saved
text preview/export keep their existing content checks.

## Reproduce

1. Use a disposable local dashboard with fictional responses and Document Agent.
   Return `{ "agent_id": "documents", "sources": null }` for its initial source
   request. The page must remain mounted, display a load error and enable Refresh
   sources while import/answer/evaluation/export remain unavailable.
2. Load a valid source list, then refresh with `sources: [null]`. The known source
   stays visible, the error appears and refresh remains available. No rendering
   crash or partial replacement occurs.
3. Start with an empty owned list and save fictional pasted text. Acknowledge the
   save, then return `sources: {}` during its list refresh. Confirm the source-saved
   notice and cleared draft remain, alongside the saved-but-refresh-failed error.
   Retry with a valid read: the source appears and there was exactly one import.
4. Reject duplicate/unsafe IDs, unsupported kinds, blank titles, malformed dates,
   URIs, approval flags or character/count limits before state application. A valid
   empty list and supported metadata with Unicode and uppercase HTTPS survive
   without rewriting values. Wrong-owner responses retain the existing owner-error
   path and cannot replace the current list.

## Validation

Three new component cases reproduced rendering crashes before the fix and now
pass. The test-only error boundary records the previous crash; it is not a new
application fallback. Twenty-one malformed-list/metadata/limit cases and one valid
metadata/empty-list case also pass. Together with initial-load and mutation recovery,
the focused run passes 37 tests.

- Full dashboard: 1,131 tests passed across 107 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; its existing suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
