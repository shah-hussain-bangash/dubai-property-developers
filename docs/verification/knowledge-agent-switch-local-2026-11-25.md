# Knowledge page agent switching — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `554e39f1824a0571356cfc74ea13fc5b7883b218` plus this change.
All sources, questions and service responses are fictional and mocked.

## Observed issue and change

Selecting another agent cleared source drafts and the displayed answer but kept
the previous agent's unsent question. That made it easy to submit an old question
under a new agent selection. The agent-change reset now clears that question too.

This is a frontend draft reset, not a change to backend source permissions or an
automatic transmission of a question. Users still explicitly submit new questions.

## Reproduction and outcomes

From apps/dashboard:

```powershell
npm.cmd test -- src/__tests__/AgentKnowledgeSwitching.test.tsx src/__tests__/AgentKnowledge.test.tsx src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Before the fix, two of the four new cases failed; two existing protections passed.
After the fix, all four pass within 16 focused Knowledge page checks:

- Selecting another agent clears the old question, title, source text and approval checkbox.
- A newly entered question is submitted only to the newly selected agent's route.
- A late source response from an aborted request cannot restore the old agent's source list.
- Agent selection remains disabled while an answer is pending and is restored on completion;
  a normally completed answer does not erase its own question.

The full frontend suite passes 894 tests in 90 files. Type checking and lint pass.
Lint reports 27 warnings in unchanged files; non-failing Vite/React test warnings
remain as documented in the previous verification. The local production build
compiles, generates routes and exits successfully, but Windows reports EPERM while
creating a dependency symlink for the standalone output. That local standalone
folder is not established as a deployable artifact; CI build/container checks
must verify the published revision independently.

## Limits

These are local component checks, not a live-browser or production incident.
Saved knowledge, backend authorization, source data and the layout are unchanged.
The unsent question is cleared on switching agents rather than retained as a
per-agent saved draft. No merge, website deployment, CRM write or customer
communication is performed.
