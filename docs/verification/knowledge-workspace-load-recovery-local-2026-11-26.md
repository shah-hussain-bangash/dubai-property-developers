# Knowledge workspace bootstrap recovery

Verified locally on 26 November 2026 against parent
`5e355148002895b98cc6bb25895f67f32bf7177b` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Verification is
from automated dashboard components with fictional responses, not a new hosted or
browser acceptance journey.

## Observed blocker and behavior

The selected-agent source read already had retry/timeout recovery, but the earlier
request loading the workspace's configured flag and agent registry did not. A
failed registry request offered only a page-refresh message, and a stalled request
had no deadline or in-page retry. The initial empty state could also imply that an
unselected agent had no sources before the registry was known.

The registry now has an explicit loading state, a 45-second deadline and **Retry
knowledge workspace** after an error or timeout. Retry reads only the workspace
index, then starts the normal selected-agent source read after success. A late
aborted registry response cannot overwrite a recovered registry. Timeout/request
handles are cleared on retry cleanup and unmount. No source operations become
available before the existing selected-agent readiness check passes.

Before applying a response, the page validates its boolean configured flag, agent
array, unique path-safe IDs of up to 100 letters/digits/underscores/hyphens, and
nonblank names of up to 200 characters. Invalid registries become retryable load
errors rather than being applied. Existing backend registry IDs satisfy this
contract; there is no fixed frontend list of 13 IDs. Future registered IDs must
meet that URL-path/filename-safe contract. The existing implementation-status
metadata is preserved and does not certify live capabilities.

A successfully loaded empty registry now shows No agents are registered in this
workspace. Before agent selection, the source-empty message is suppressed. Existing
unconfigured-storage notices and source-level recovery continue to work.

This is a dashboard bootstrap/readiness fix. API schemas, permissions, agent/source
ownership, stored data, evaluation files, model behavior and delivery are unchanged.
It does not reconnect hosting, fix authentication or prove source answer quality.
The index is read on initial load and manual retry only; no polling is added.

## Reproduce

1. Start the disposable local mock-provider dashboard with a fictional registered
   Document Agent and an empty owned source list. Make the workspace-index request
   (`GET /api/v1/knowledge/agents`) fail.
2. Confirm a workspace load error and Retry knowledge workspace appear. Knowledge
   actions remain disabled and the page does not claim an empty selected source
   list. Retry with a valid response: Document Agent is selected, its source list
   loads, the error clears and the normal controls become available. Only reads
   occur; no import, review, removal or customer message is sent.
3. Hold the initial index request unresolved and advance the component's test timers
   45 seconds. Its signal is aborted and a retry is available. Recover, then resolve
   the first request with an obsolete different agent: the recovered selection and
   options remain intact. These are test timers, not machine-clock changes.
4. Unmount while loading: the registry request and timer are cancelled.
5. Return a valid empty registry: the explicit no-registered-agents status appears,
   with source actions disabled. Return malformed data, duplicate/path-unsafe IDs
   or blank names: no agent list is applied and no source request starts; retry is
   offered. Storage configured false with a valid registry retains its existing
   administrator-configuration notice.

## Validation

Four new recovery/empty-state component cases failed before implementation and now
pass. Seven additional malformed-registry cases pass. The combined workspace,
selected-source loading and mutation-recovery run passes 23 tests.

- Full dashboard: 1,106 tests passed across 106 files. Type checking and production
  compilation passed. Lint has zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing backend suites run in GitHub CI.
- No merge or deployment is included. Hosted verification remains pending hosting
  access recovery and the normal release checks.
