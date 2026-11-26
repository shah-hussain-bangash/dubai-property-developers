# Dubai Property Developers capability and demonstration guide

This portfolio demonstrates a public property website, controlled enquiry handoff
and separate supplied knowledge for 13 agent identities. The strongest evidence is
the recorded local acceptance below. The separately hosted website may run a
different revision and has not passed the complete hosted acceptance journey.

## Open the guided demonstration

The [seven-step walkthrough](portfolio-demo.html) presents original fictional test
captures with captions and links to evidence. It is an interactive screenshot
presentation, not a recording of a live hosted session. It needs no application
credentials, API, database, model or external website.

From the repository root, serve only the documentation directory:

```text
python -m http.server 3119 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:3119/case-study/portfolio-demo.html`. Use Next/Previous, the
numbered steps or left/right arrow keys. Full-size captures are available from
each slide. Stop the local server with Ctrl+C when finished. Opening the HTML
directly from a checkout also uses its relative screenshot links.

[Walkthrough verification and preview](../verification/portfolio-package-local-2026-11-26.md)
record the browser navigation, image, link and script checks.

## Suggested presentation sequence

1. Show the saved receipt and explain enquiry-only permission.
2. Show Admin's actual enquiry queue and assignment to an approved operator.
3. Show Alpha's client brief, retained receipt/message and recorded ownership.
4. Show Beta's empty workspace to explain operator separation.
5. Show an agent's exact PDF excerpt and page citation.
6. Show the explicit no-answer response for another agent's source.
7. Show that deleting knowledge removes it from subsequent answers.

The takeaway is traceable records and controlled source use. Do not present the
fictional enquiry as a sale, the budget as a valuation, or the demonstrations as
measured business conversion improvements.

## Verified behavior

| Area | Current demonstrated behavior | Evidence |
| --- | --- | --- |
| Website to operations | Anonymous enquiry, recorded consent/provenance, Admin assignment, owned brief and other-operator exclusion | [Local browser journey](../verification/website-operations-local-2026-11-26.md), revision `0d6f4c4`; 36 focused tests |
| Agent knowledge | PDF, Markdown, one-page website snapshots and pasted text; exact excerpts/citations or explicit no-answer | [All-agent acceptance](../verification/all-agent-knowledge-acceptance-local-2026-11-26.md), revision `4477bec`; 52 sources and 91 browser questions |
| Knowledge boundaries | Separate agent/organization ownership, customer approval, persistence and deletion | Same acceptance: 624 cross-agent and 52 cross-organization abstentions; removal survives app restart |
| Container storage | Prepared non-root dashboard directory and persistent Compose volume | [Storage review](../verification/phase1-deployment-compatibility-local-2026-11-26.md); real CI write/read across replacement containers |
| Optional conversation persistence | SQLite history/state retains scoped WhatsApp opt-outs across runtime restart; API/worker share a dedicated Compose volume | [Durable memory verification](../verification/durable-agent-memory-local-2026-11-26.md); configuration requires a writable private path |
| Question wording | Supplied-source retrieval supports listed English question wrappers, singular/plural forms and spelling variants while preserving quoted excerpts | [Wording verification](../verification/supplied-question-wording-local-2026-11-26.md); this is bounded lexical matching |
| Separate evaluation data | Agent-bound question files, expected passage/no-answer checks and downloadable actual citations; examples never enter knowledge | [Local evaluation workspace](../verification/agent-knowledge-evaluation-local-2026-11-26.md); 29 API and 19 dashboard regressions, fictional browser save/reload journey |
| Customer evaluation checks | Saved per-agent sets select staff or approved-source customer retrieval, retain the audience in files and verify result audiences; no customer delivery | [Local customer evaluation](../verification/customer-knowledge-evaluation-local-2026-11-26.md); 20 new API and 14 dashboard cases |
| Source review deadlines | Optional date for every import method, saved deadline display, expiry exclusion and explicit re-import renewal | [Review-date lifecycle](../verification/source-review-dates-local-2026-11-26.md); 49 API and seven dashboard regressions plus a local browser rehearsal using simulated days |
| Saved text review | Staff read their selected agent's saved extracted text with PDF page numbers, including overdue sources; no renewal or approval side effects | [Saved text preview](../verification/saved-source-preview-local-2026-11-26.md); 53 API and 11 dashboard regressions plus a fictional local browser journey |
| Existing source renewal | Explicit staff review changes the saved deadline without re-upload; customer approval resets unless explicitly selected | [Source renewal](../verification/saved-source-review-local-2026-11-26.md); 38 API and nine dashboard regressions, including customer retrieval and local browser confirmation |
| Source review history | Authenticated reviewer, time and previous/new values recorded atomically; scoped pages of 20 records | [Review history](../verification/source-review-history-local-2026-11-26.md); 22 API/storage and 15 dashboard regressions, including rollback, concurrency and a local browser journey; deletion removes associated history |
| Source review queue | Manual selected-agent check for overdue and seven-day due sources, with server-date counts and direct source review | [Queue verification](../verification/source-review-queue-local-2026-11-26.md); 14 API and 15 dashboard regressions plus a fictional before/after renewal journey; no scheduled notifications |
| Customer knowledge preview | Staff-controlled question mode quotes only current, customer-approved own sources, with audience validation and explicit abstention | [Customer preview](../verification/customer-knowledge-preview-local-2026-11-26.md); 21 API and 10 dashboard regressions plus a fictional PDF/staff-only/approval-withdrawal journey; no customer delivery |
| Automated validation | Backend/frontend tests, database integration, image builds, Windows setup and security/configuration checks | [PR 87 checks](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87/checks); 12 checks passed at evidence revision `8ea55a8` |

Acceptance revisions identify the source used for each run. Later documentation
commits do not establish a new deployed application revision. Local test counts
in the records are distinct from hosted CI results; skipped/expected failures
are not counted as passes.

## Agent capabilities

All identities have separate knowledge scopes and evaluation data. Their
operational capabilities remain different:

| Agent | Operational status | Current scope |
| --- | --- | --- |
| Supervisor | Functional rules | Intent routing and escalation plans |
| Lead Intake | Functional rules | Normalization, sanitization and duplicate lookup |
| Qualification | Functional rules | Explainable, uncalibrated scoring and queue routing |
| Property Recommendation | Functional with fictional catalog | Filter/rank supplied structured listings; source-only workspaces start without demo listings |
| CRM | Functional with mock provider | Local save, CRM create/update and qualification note; live adapter validation pending |
| Sales Conversation | Partial | Own-source cited drafts and escalation, with human approval |
| Follow-Up | Partial | Due-task checks and approved mock dispatch; persistent task loading/scheduler pending |
| Email | Partial | Own-source drafts and mock sending; approval and relevant consent checks |
| WhatsApp | Partial | Own-source replies, opt-in/opt-out and service-window checks; live account validation pending |
| Marketing | Partial | Consent-filtered planning and own-source drafts; no campaign sending |
| Documents | Partial | Own-source extractive answers and summaries |
| Analytics | Partial | Scoped lead summaries and execution-record reporting |
| Voice AI | Interface only | Contract/transcript paths; no implemented speech-to-text or calling provider |

The [agent implementation guide](../agents/README.md) defines the detailed contracts.
Optional OpenAI/Ollama adapters exist, but the current agents use rules, templates
and extracted passages rather than generative model answers. Importing knowledge
does not fine-tune a model or silently change an agent's routing/scoring rules.

## Reproduce the application evidence

Use the recorded revision, a new private data directory and fictional accounts.
Follow the [enquiry reproduction](../verification/website-operations-local-2026-11-26.md#reproduction-and-remaining-dependency)
and [knowledge reproduction](../verification/all-agent-knowledge-acceptance-local-2026-11-26.md#reproduction).
The [Windows setup](../development/windows-setup.md) and
[Docker guide](../deployment/docker.md) describe the development environment.
Keep source fixtures separate from evaluation questions and expected answers.

## Remaining work before a shared or live release

- Review and approve the complete PR, select the release revision and verify the
  actual hosted revision and eligible synthetic operator access.
- Back up existing portal/source data and rehearse migration/rollback. A new
  volume does not automatically contain an old container's records.
- Reconcile old action approvals/replay keys; default conversation memory,
  consent, approvals and replay cache remain process-local.
- Verify the hosted identity configuration. Local development principals and
  fictional token verifiers do not certify production authentication.
- Validate live providers in authorized sandbox accounts. Calendar and telephony
  remain mock/interface capabilities; partner property APIs require authorized access.
- Plan durable scheduling/consent, monitoring, recovery and the documented
  cross-system database/queue fencing limitation before live business use.

See the [completion guide](../development/portfolio-completion-guide.md) for phase
status. This package makes the local portfolio evidence reviewable; it does not
merge, deploy, migrate existing data or enable external delivery.
