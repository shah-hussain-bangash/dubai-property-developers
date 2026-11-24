# Dubai Property Developers

## From website enquiry to an owned client brief

**Shah Hussain Bangash · Dubai, UAE**  
**Scope:** Portfolio demonstration of full-stack architecture and a fictional software workflow. Hosted CI, source review and a disposable local browser run provide the evidence below.

### The business problem

A visitor can ask about a property without creating an account. The operations team needs a stable record of the enquiry, its source and the visitor's permission. An approved agent should see only their assignments and should be able to create a client brief once the enquiry has been reviewed.

### My engineering contribution

I separated anonymous intake, admin assignment and agent-owned conversion. I designed the handoff around a saved enquiry reference and a versioned record, so a browser retry can return the same reference and an old staff screen cannot overwrite a newer decision. The conversion operation creates the client brief and links it to the enquiry together.

```mermaid
flowchart LR
  A["Public enquiry form"] --> B["Saved enquiry and reference"]
  B --> C["Admin inbox"]
  C --> D["Assigned agent"]
  D --> E["Owned client brief"]
```

### One fictional case

| Stage | What the application does |
| --- | --- |
| Intake | A visitor asks about a Dubai Marina apartment, provides example contact details and grants permission for that enquiry. The form submits with a short-lived ticket. |
| Acknowledgement | The visitor receives a reference. Retrying the same ticket returns the existing receipt without changing the record. The acknowledgement stays in the portal. |
| Assignment | An admin opens the shared enquiry inbox and assigns an approved agent using the current record version. |
| Review | The assigned agent checks property interest, budget and permission. Access is removed when approval is revoked. An opted-out, closed or spam enquiry cannot be converted. |
| Conversion | The agent creates a client brief and the portal links it back to the enquiry. Competing conversions leave one owned brief. |

### Architecture and trade-offs

- **Ownership follows authenticated identity.** Matching an email address cannot attach an anonymous enquiry to a member account. Approved agents receive only their own assignments.
- **A reference is operational evidence.** The form shows a receipt after persistence succeeds. Email delivery, CRM synchronization and outbound messaging require separate integration validation.
- **Keep intake and AI assistance independently verifiable.** The product includes a FastAPI workflow layer and optional model adapters. The website-to-client-brief case follows the Next.js enquiry routes and portal store. It demonstrates deterministic controls on the core record handoff.

### What was verified

| Evidence | What it supports |
| --- | --- |
| [Connected enquiry store and handler tests](../../apps/dashboard/src/__tests__/ConnectedEnquiries.test.ts) | Tests cover receipt deduplication, role-scoped visibility, stale edits, revocation, opt-out handling and concurrent conversion using fictional fixtures. |
| [Enquiry UI tests](../../apps/dashboard/src/__tests__/ConnectedEnquiryViews.test.tsx) | Component tests use mocked responses to check consent submission, failure feedback and assignment with the current version. |
| [Local browser journey on 24 November 2026](../verification/website-operations-local-2026-11-24.md) | At revision `c3f49e8`, one fictional enquiry retained its consent and source, was assigned to Alpha, and became an Alpha-owned brief. Beta saw neither record. The 36 focused tests passed before and after the run. This is local evidence; hosted staging remains unverified. |
| [GitHub Actions run 44871320870](https://github.com/shah-hussain-bangash/dubai-property-developers/actions/runs/44871320870) | All 10 reported jobs passed on 21 November 2026 for commit [`f24771d`](https://github.com/shah-hussain-bangash/dubai-property-developers/commit/f24771ddbf12e08c2f607b291d15ec73ec98260f). This is a dated project CI baseline; the separate local run above covers the enquiry workflow at its recorded revision. |

[Enquiry implementation notes](../connected_website_enquiries.txt) · [Portal store](../../apps/dashboard/src/lib/agentPropertyStore.ts) · [System architecture](../../ARCHITECTURE.md)

### Portfolio scope and optional follow-up

The captured local journey, synthetic records, screenshots and focused tests are the evidence for this portfolio case. The public demo is available for viewing; it is not evidence that the complete hosted journey has passed.

A read-only hosted Admin check on 24 November 2026 found zero registered members, approved agents or access requests. The API identified itself as staging, but the deployed Git revision was not established. No new hosted enquiry or account was created. A future hosted verification would need synthetic operator access and a confirmed deployed revision. Provider delivery and measured conversion improvements remain unverified.
