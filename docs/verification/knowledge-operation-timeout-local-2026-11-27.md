# Bounded knowledge operations and late-result isolation

Verified locally on 27 November 2026 against parent
`9fa87fcd91527c951c58a8602d4f50af1c0f15b5` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All responses and
files are fictional component fixtures; no new hosted/browser acceptance or live
provider journey is claimed.

## Observed blocker

The main Knowledge operation runner's 45-second timer only aborted its signal while
continuing to await the action. A local File.text read does not consume that signal;
an unresolved read could leave the workspace busy indefinitely. The same happened
with a request that ignored abort. Simply releasing busy would also permit delayed
answers or mutation acknowledgements to overwrite a recovered/new agent view.

## Behavior and limits

The runner now races the action against an abort-aware wait. At its existing
45-second deadline it aborts the signal, ends its UI wait, releases the busy lock,
closes any pending removal confirmation and marks the selected source view unready.
The page asks for Refresh sources to check current state before trying again.
Knowledge actions stay disabled until that owned list read succeeds. Agent selection
can move to another scope and run its normal initial read.

Every affected async completion checks cancellation before changing UI state:
answers, saved-text previews (including review-queue navigation), source-save,
removal and review acknowledgements, and evaluation reports. Existing export and
question-file load guards remain. A delayed abandoned action cannot clear a draft,
show success, insert old text/results, change refreshed source metadata, remove a
row or unlock a newer operation. Only the runner owning the active controller can
release its lock. Unmount aborts the active wait and clears the timer/listener
without posting state/error changes to the disposed view.

Timed-out mutations are not automatically repeated. Upload drafts remain when the
acknowledgement arrives only after timeout. If a mutation was already confirmed
before its subsequent list read timed out, its existing confirmed notice can remain;
the read needs reconciliation. The UI error does not assert that the whole write
failed. File questions/expected passages remain separate from source knowledge.

This bounds the UI wait; it does not forcibly interrupt File.text, cancel server
processing, undo writes or establish exactly-once delivery. A backend operation may
finish after timeout, or even after an early refresh, so check the actual record
state before another write. No server-side cancellation/reconciliation protocol,
API schema, permission, source ownership or delivery policy is added. Existing
workspace-index/source-load deadlines and independent coverage/history/queue
request handlers remain separate.

## Reproduce

1. Start a disposable local mock-provider dashboard, load Document Agent and begin
   loading a small valid question file whose text promise is held unresolved.
2. Advance the component test timers 45 seconds. Confirm a did-not-finish error,
   enabled Agent/Refresh sources controls, and disabled knowledge actions. Refresh
   successfully; Run saved checks becomes available again. Resolve the old file
   afterward: its late questions must not replace the current editor.
3. Repeat with an answer request held past its deadline. Switch to Marketing Agent
   and resolve the old Document Agent answer: no old answer appears.
4. Hold a pasted-text upload past timeout, refresh, then return a valid saved-source
   acknowledgement. The original draft remains and no late success is shown. There
   was exactly one POST; no automatic retry occurs.
5. Repeat for saved-text preview and evaluation report reads. After recovery, late
   old content/results stay hidden. Repeat for DELETE and review PATCH: late
   acknowledgements cannot remove a refreshed row or change its deadline/notice,
   and no second mutation is issued.
6. After timing out one question, refresh and start a new pending question. Resolve
   the old one: the newer operation stays locked and its answer is not replaced.
   Resolve the newer one: only its valid answer appears and the lock releases.
7. Unmount during a stalled operation: its signal is aborted and no deadline remains.
   A later response produces no disposed-view error or rendered result. Test timers
   are used throughout; machine time and production settings are untouched.

## Validation

The first three new component regressions failed before implementation and now pass.
Six additional cases cover preview/report/review/removal completion, newer-lock
ownership and unmount cleanup: nine new cases total. The focused operation, initial
load, mutation-recovery and save/removal-acknowledgement run passes 39 tests. Tests
use requests/file reads deliberately ignoring abort to verify release does not depend
on cooperation, and inspect actual UI state plus mutation counts.

- Full dashboard: 1,165 tests passed across 111 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
