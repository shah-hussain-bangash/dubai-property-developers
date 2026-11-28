# Knowledge citation metadata — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `98581af238600a7dfa39956d08ff33647b0d0df3` plus this change.
All references, questions and service responses are fictional and mocked.

## Observed issue and change

The frontend verified quote text but did not validate citation page metadata.
A malformed response could display Page -2, a fractional page or a text value.
Empty citation titles/IDs were accepted, and null citation entries caused a raw
property-access error rather than a bounded verification message.

The answer parser now requires each citation to be an object with nonempty title
and source ID. Page values must be null or an integer from 1 to 100, matching
the current PDF import limit. Invalid citations reject the complete answer and
show the existing reference-verification error rather than misleading provenance.

## Reproduction and outcomes

From apps/dashboard:

```powershell
npm.cmd test -- src/__tests__/AgentKnowledgeCitations.test.tsx src/__tests__/AgentKnowledgeSwitching.test.tsx src/__tests__/AgentKnowledge.test.tsx src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Before the fix, 13 of the 16 new cases failed; three valid-page cases passed.
After it, all 16 pass within 32 focused Knowledge page checks. Coverage includes
zero, negative, fractional, over-limit, string, boolean and missing page values;
null citations; blank title/identity fields; supported page boundaries/null; and
a component check that an invalid citation does not render the answer.

The complete frontend suite passes 910 tests in 91 files. Type checking and lint
pass; lint retains 27 warnings in unchanged files. Non-failing Vite/React warnings
remain in the test output. Local production compilation completes successfully;
the previously recorded Windows standalone-packaging permission limitation remains
separate from CI build verification.

## Limits

This checks citation shape and range, not whether an actual page contains a quoted
statement or whether a well-formed source ID belongs to a user. Existing backend
source ownership and excerpt checks remain authoritative. A future change to the
100-page upload limit must update the frontend contract too. No layout change,
merge, deployment, real CRM write or customer communication is performed.
