# Knowledge import method transitions — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `992cfe828d80d6895bb0f22ce004ab14a0fb49fb` plus this change.
All files, source text, URLs and requests in these component tests are fictional.

## Observed issues

Changing between file, website and pasted-text input retained the customer-answer
approval checkbox from the previous method. A newly selected file could therefore
be submitted as customer-approved without checking the box again. The internal
file selection also survived after leaving the file picker; direct form-handler
submission could reuse it even though the visible picker had changed. Native
browser required-file validation was already a separate check.

React also reused the file and URL input elements across modes, producing a
controlled/uncontrolled input warning.

## Change

Method changes reset customer approval and file selection. File and URL controls
have distinct React identities so each keeps the correct input lifecycle. A fresh
file must be selected after returning to upload mode; text, URL and title drafts
remain available when returning to their method. Customer approval can be granted
again explicitly for the current source.

## Reproduction and outcomes

From apps/dashboard:

```powershell
npm.cmd test -- src/__tests__/AgentKnowledgeImportModes.test.tsx src/__tests__/AgentKnowledgeCitations.test.tsx src/__tests__/AgentKnowledgeSwitching.test.tsx src/__tests__/AgentKnowledge.test.tsx src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Before the fix, nine of ten new cases failed. After it, all ten pass within 42
focused Knowledge page checks. They cover all six method transitions, stale-file
handler rejection, fresh-file submission with customer approval off, retained
typing drafts and the absence of controlled/uncontrolled input warnings.

The full frontend suite passes 920 tests in 92 files. Type checking and lint pass;
27 lint warnings remain in unchanged files. Local production compilation completes
successfully with the previously recorded Windows standalone-packaging permission
limitation. Independent CI build verification is required for the published revision.

## Limits

This is local component verification, not a live-browser or production incident.
No previously saved source approval is changed; the reset concerns an unsaved
import form. Saved knowledge permissions and outbound-message approval checks
remain separate. No merge, deployment, real CRM write or customer communication
is performed.
