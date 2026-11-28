# Phase 1 dashboard mutation recovery review

Local verification on 26 November 2026 of parent
`b59cae03af3fd0aeacd78bc4bea8d8033eaf7812` plus this change in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
All API requests are component-test mocks; no hosted source is modified.

## Confirmed issue and change

The Knowledge page treated a successful import/removal followed by a failed list
refresh as one failed operation. After import, the draft and customer-use approval
remained selected despite the completed save. After removal, the old source and
confirmation remained visible despite its completed deletion. Initial list failures
also displayed the empty-list claim, although no empty result had been received.

Confirmed import acknowledgements now clear the submitted draft and approval and
retain a saved notice before attempting the refresh. A refresh failure states
explicitly that the source was saved and asks the operator to refresh the list.
Confirmed deletions remove that item from the displayed list, clear confirmation
and retain a removal notice before refreshing. Refresh failures do not claim the
list is empty. The existing Refresh sources action remains available.

An import request that fails retains its draft, and a removal request that fails
retains the source. This change distinguishes an acknowledged mutation from its
subsequent read; it does not infer success when a request times out or loses its
acknowledgement. Backend authorization and saved source permissions are unchanged.

## Review and regression evidence

Reviewed the Knowledge panel and its request/answer parsing helper, including
agent selection, in-flight control locking, draft approval resets, source links,
citation checks, mutation errors and refresh recovery.

New file: `apps/dashboard/src/__tests__/AgentKnowledgeMutationRefresh.test.tsx`.
The original five recovery cases fail against the pre-change panel and pass after
the fix. Two additional cases preserve genuine import/removal failure behavior.
All **seven new cases pass** within **77 focused Knowledge checks in eight files**.
The file-upload test submits the form explicitly after selecting a synthetic File;
this avoids relying on jsdom's native file-input constraint validation.

Coverage includes file/website/pasted-text imports with post-save read failures,
draft/approval reset, explicit notices, no repeated POST on successful list retry,
post-delete read failure, genuine mutation failure and initial read failure.

From apps/dashboard:

```text
npm.cmd test -- src/__tests__/AgentKnowledgeMutationRefresh.test.tsx src/__tests__/AgentKnowledge.test.tsx src/__tests__/AgentKnowledgeSourceApproval.test.tsx src/__tests__/AgentKnowledgeImportModes.test.tsx src/__tests__/AgentKnowledgeCitations.test.tsx src/__tests__/AgentKnowledgeSwitching.test.tsx src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx src/__tests__/AgentKnowledgeSourceLinks.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

The full frontend suite passes **955 tests in 95 files**. Production compilation
completes with exit 0 and the existing Windows packaging warning described below.
Type checking and lint pass; 27 existing lint warnings remain in unchanged files.
Local tests retain the existing Vite configuration warning. Production artifact
packaging on Windows has a previously documented dependency symlink limitation;
the local standalone folder is not a verified deployment artifact.

This is local automated UI evidence, not a hosted browser acceptance run. Remaining
Phase 1 work is deployment/data compatibility review. Hosted revision and synthetic
operator access remain unconfirmed. No merge, deployment or customer communication
is performed.
