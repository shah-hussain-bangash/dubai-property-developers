# Knowledge source link verification — local, 25 November 2026

Repository: shah-hussain-bangash/dubai-property-developers, PR #87.
Revision: parent `9f2baca4bf281d883200486bae51548af1c808f1` plus this change.
All source responses and links are fictional; no external page is opened.

## Observed issues and change

The Knowledge page's case-sensitive HTTPS display check hid valid uppercase HTTPS
links. A separate backend check with mocked DNS confirmed that public_target accepts
that scheme casing. The frontend answer parser also accepted malformed URI types
and unsupported URL metadata. Synthetic responses could consequently render an
unverified link; this is not evidence that the backend returned such a response.

Source URI metadata must now be null or a parseable absolute HTTPS URL without
embedded credentials, a nondefault port, a nonempty fragment or ASCII whitespace/
control characters. The display check accepts HTTPS scheme casing consistently.
Validation does not rewrite the saved URI; encoded and Unicode links remain intact.
Sources without a link retain null metadata.

## Reproduction and outcomes

From apps/dashboard:

```powershell
npm.cmd test -- src/__tests__/AgentKnowledgeSourceLinks.test.tsx src/__tests__/AgentKnowledgeSourceApproval.test.tsx src/__tests__/AgentKnowledgeImportModes.test.tsx src/__tests__/AgentKnowledgeCitations.test.tsx src/__tests__/AgentKnowledgeSwitching.test.tsx src/__tests__/AgentKnowledge.test.tsx src/__tests__/AgentKnowledgeUncitedAnswer.test.tsx
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

Before the fix, 15 of 20 new cases failed and five valid metadata cases passed.
After it, all 20 pass within 70 focused Knowledge page checks. The component cases
verify an uppercase link's original href, new-tab safety attributes, and rejection
of an answer containing login-bearing link metadata. Other cases cover malformed
types, unsupported schemes, controls, ports, fragments, encoded paths and Unicode.

The full frontend suite passes 948 tests in 94 files. Type checking and lint pass;
27 lint warnings remain in unchanged files. Local production compilation completes
successfully with the documented Windows standalone-packaging permission limitation.
CI builds verify the published revision independently.

## Limits

Client format validation does not establish public DNS resolution, availability,
source ownership or agreement between a link and the quoted page. Backend source
authorization and website-import network checks remain authoritative. No merge,
deployment, real CRM write or customer communication is performed.
