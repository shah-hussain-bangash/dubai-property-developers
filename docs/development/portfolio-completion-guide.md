# Dubai Property Developers completion guide

Start with a reviewable portfolio release, then verify its demonstration. Live business
integrations are a later phase. Use fictional records and mock providers throughout
this plan. Merging and deployment require a separate release decision.

## Phase 1 Review the release candidate

Baseline checked on 26 November 2026:

- Repository: `shah-hussain-bangash/dubai-property-developers`.
- [PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87)
  is open and unmerged, with 48 commits and 136 changed files.
- Candidate revision: `c517a6cb584d89975c9a51bf45435db9b0cb348c`.
- Base revision: `4f4b404d3762df3e12596cbeba41311dd18fa2ac`.
- All 11 GitHub checks pass at the candidate revision. This includes backend,
  database integration, frontend, Windows setup and security/configuration checks.
- The existing local candidate snapshot passes all 36 enquiry store/UI tests in
  a fresh focused run. This is automated local evidence, not a new browser journey.

Review the complete diff in these groups before calling this phase complete:

1. Agent and organization boundaries: source access, memory, actions and approvals.
   Initial bounded review complete with 159 local checks passing; see the
   [review record](../verification/phase1-agent-boundary-review-local-2026-11-26.md).
   Private deployment identity verification remains a release dependency.
2. External actions: consent, retries, CRM identity and calendar ownership.
   Initial review found malformed creation acknowledgements; the fix and 43 new
   regression cases pass within 386 focused tests. See the
   [external action record](../verification/phase1-external-actions-local-2026-11-26.md).
   Live provider behavior and reconciliation remain separate release conditions.
3. Knowledge import: files, HTML, Unicode links, deadlines and source review dates.
   Initial review found that truncated website responses could be saved. The fix
   and eight new cases pass within 124 focused checks. See the
   [knowledge import record](../verification/phase1-knowledge-imports-local-2026-11-26.md).
4. Dashboard: agent switching, source approval resets and citation rendering.
5. Compatibility: existing configuration, saved data and outstanding approvals.

Important release conditions:

- Agent-scoped action keys changed. Reconcile persisted pending/completed actions
  before rollout; do not replay an old delivery ledger blindly. See
  [action isolation](../verification/agent-action-isolation-local-2026-11-24.md).
- Conversation memory remains process-local by default. SQL legacy state needs an
  ownership review; this candidate does not migrate it automatically.
- Back up the private source SQLite volume separately from portal/PostgreSQL data.
  Confirm a writable persistent `AGENT_KNOWLEDGE_PATH` for the chosen environment.
- Local Windows compilation passes with a standalone symlink packaging warning.
  Use a verified build artifact; do not deploy the local standalone folder.

Phase exit: record reviewed revision, unresolved findings and compatibility decisions.
Passing CI establishes a baseline; the complete diff review is still pending.

## Phase 2 Verify the selected environment

First identify the actual running revision and use isolated synthetic Admin and
approved operator accounts. The hosted revision and eligible operator access are
unconfirmed. If unavailable, use a disposable local environment and label all
evidence local.

Repeat [the enquiry journey](../verification/website-operations-local-2026-11-24.md):
submit one fictional enquiry, retain consent and receipt, assign an eligible
operator, create its client brief, and verify source linkage and ownership. A second
operator must see neither owned record. Record the tested revision and evidence.

Phase exit: one traceable enquiry and owned brief on the selected revision, with
no CRM writes or outbound messages.

## Phase 3 Accept each agent's knowledge behavior

For each of the 13 agents, use a distinct fictional fact and independent expected
answers. Exercise PDF, website snapshot and pasted text; keep evaluation questions
separate from source material. Verify correct citations, unrelated-question
abstention, cross-agent exclusion, restart persistence and source removal.
Customer use must require explicit source approval. Staff previews send nothing.

Automated all-agent source-format coverage already exists; repeat the visible
acceptance checks on the selected release revision. Sources support excerpt-based
answers, not model training, voice calls or automatic changes to routing rules.

Phase exit: an evidence table for all agents with failures resolved or documented.

## Phase 4 Prepare the portfolio demonstration

Update the case study and screenshots to the verified revision. Record a short
demonstration of enquiry ownership and separate agent knowledge. Distinguish
functional, partial and interface-only capabilities. Keep setup instructions
reproducible with fictional fixtures.

Phase exit: a reviewer can reproduce the demonstrated behavior from the guide.

## Later development for live business use

Plan separate work for durable runtime storage and consent, scheduled follow-ups,
production authentication, sandbox provider validation, monitoring and recovery.
Voice/telephony, live calendar and partner property APIs require additional
implementation or authorized access. Better paraphrase retrieval needs independent
quality evaluations. These are not prerequisites for an accurately labelled
portfolio demonstration.
