# Knowledge source edit approval — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `b00584a71f1845cee16985288cd088745f20708d` plus this change.
All files, source text, links and requests in these component tests are fictional.

## Observed issue and change

Customer-answer approval remained checked after replacing the selected file or
editing the source link, pasted content or title. A draft's changed material could
therefore inherit the previous checkbox decision within the same input method.

Those four source-field edits now reset the checkbox. The page explains that
editing source details clears the approval. The operator can explicitly approve
the completed draft again, or save it for staff-only questions. Editing only the
test question does not change approval for an otherwise unchanged source draft.

## Reproduction and outcomes

From apps/dashboard:

```powershell
npm.cmd test -- src/__tests__/AgentKnowledgeSourceApproval.test.tsx src/__tests__/AgentKnowledgeImportModes.test.tsx src/__tests__/AgentKnowledgeCitations.test.tsx src/__tests__/AgentKnowledgeSwitching.test.tsx src/__tests__/AgentKnowledge.test.tsx src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Before the fix, four of eight new cases failed. After it, all eight pass within
50 focused Knowledge page checks. The regression verifies both the checkbox and
the actual submitted payload: replacement files, links, text and titles are saved
with customer approval false. Explicit approval after final edits still submits
true for all three import methods. Question edits alone send no request and do
not revoke the current draft's approval.

The full frontend suite passes 928 tests in 93 files. Type checking and lint pass;
27 lint warnings remain in unchanged files. Local production compilation completes
successfully with the previously documented Windows standalone-packaging permission
limitation. CI builds verify the published revision independently.

## Limits

This is a frontend draft safeguard, not a cryptographic approval receipt or a
change to server-side source-management permissions. Editing an unsaved form makes
no server change to existing sources. Saving or re-importing a source retains the
existing backend semantics. No merge, deployment, real CRM write or customer
communication is performed.
