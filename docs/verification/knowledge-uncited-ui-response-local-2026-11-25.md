# Knowledge page uncited-response check — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `e185163b0de7d791782e349365a684845a4e0343` plus this change.
All service responses and document claims in these tests are fictional.

## Observed blocker

The frontend checked that an answered response exactly matched its cited excerpts,
but accepted arbitrary response text when answered=false and sources was empty.
A simulated malformed response therefore displayed an unsupported payment claim
under the no-answer heading. This was a frontend verification gap; the test does
not establish that the backend generated an unsupported claim.

## Change

An unanswered response must now contain the backend's fixed no-answer message.
Other text is rejected with a bounded verification error, and no answer is rendered.
Valid no-answer responses remain accepted. Existing owner, citation and exact-quote
checks continue to apply to answered responses.

The fixed frontend message was compared with knowledge.assigned_sources.NO_ANSWER
and matches exactly. A future change to that response text must update both sides.
No source import, agent-selection, retrieval or outbound-message behavior changed.

## Reproduction and results

From apps/dashboard:

```powershell
npm.cmd test -- src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx src/__tests__/AgentKnowledge.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Before the fix, five of the six new regression cases failed; the canonical no-answer
case passed. After the fix, all six pass within 12 focused Knowledge page tests.
The component regression checks that the unsupported claim is not displayed and
that the verification error is shown instead. Existing PDF upload, website/text
import, agent switching, citations and deletion checks also pass.

The complete frontend suite passes 890 tests in 89 files. Type checking and the
production build pass. Lint passes with 27 warnings in
unchanged files. Test output also includes non-failing Vite/React warnings.

## Limits

This is local component/service verification with mocked responses, not a live
backend incident or a production-browser result. No application layout change,
merge, website deployment, real customer message or CRM write is performed.
