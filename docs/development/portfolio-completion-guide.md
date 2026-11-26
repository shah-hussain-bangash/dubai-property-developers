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
   Initial review found misleading recovery after a successful save/removal and
   failed list refresh. Seven new cases pass within 77 focused checks. See the
   [dashboard recovery record](../verification/phase1-dashboard-recovery-local-2026-11-26.md).
5. Compatibility: existing configuration, saved data and outstanding approvals.
   Initial review found missing writable/persistent dashboard storage. The image
   and Compose fix add a real container-replacement check; 95 local tests and a
   separate synthetic knowledge backup/restore rehearsal pass. See the
   [compatibility record](../verification/phase1-deployment-compatibility-local-2026-11-26.md).

Important release conditions:

- Agent-scoped action keys changed. Reconcile persisted pending/completed actions
  before rollout; do not replay an old delivery ledger blindly. See
  [action isolation](../verification/agent-action-isolation-local-2026-11-24.md).
- Conversation memory remains process-local when `AGENT_MEMORY_PATH` is unset.
  Optional SQLite memory now retains scoped history/state and conversation opt-outs.
  Existing memory and SQL legacy state require an ownership/cutover review; they
  are not migrated automatically.
- Back up the private source SQLite volume separately from portal/PostgreSQL data.
  Confirm a writable persistent `AGENT_KNOWLEDGE_PATH` for the chosen environment.
- Local Windows compilation passes with a standalone symlink packaging warning.
  Use a verified build artifact; do not deploy the local standalone folder.

Phase exit: record reviewed revision, unresolved findings and compatibility decisions.
Passing CI establishes a baseline. All five initial review groups have records;
full PR sign-off and environment-specific release conditions remain pending.

## Phase 2 Verify the selected environment

Candidate revision `0d6f4c4` passed the local browser journey on 26 November 2026,
with one consented enquiry, an Alpha-owned brief and no Beta visibility. All 36
focused tests pass. See the [candidate acceptance evidence](../verification/website-operations-local-2026-11-26.md).
Hosted acceptance remains pending the dependencies below.

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

Local acceptance passed for all 13 agents at revision `4477bec` on 26 November
2026: 52 four-format sources, 91 browser questions, scoped abstention, approval
boundaries and removal/restart checks. Existing evaluation/regression runs pass
112 tests. See the [acceptance matrix and evidence](../verification/all-agent-knowledge-acceptance-local-2026-11-26.md).
Hosted acceptance remains pending; live provider capabilities are unchanged.

For each of the 13 agents, use a distinct fictional fact and independent expected
answers. Exercise PDF, website snapshot and pasted text; keep evaluation questions
separate from source material. Verify correct citations, unrelated-question
abstention, cross-agent exclusion, restart persistence and source removal.
Customer use must require explicit source approval. Staff previews send nothing.

Automated and visible checks above cover the recorded local revision. Repeat
acceptance on a later selected release revision. Sources support excerpt-based
answers, not model training, voice calls or automatic changes to routing rules.

Phase exit: an evidence table for all agents with failures resolved or documented.

## Phase 4 Prepare the portfolio demonstration

The [guided screenshot demonstration](../case-study/portfolio-demo.html), updated
case study and [capability guide](../case-study/PORTFOLIO_CAPABILITIES.md) package
the verified local evidence. The seven steps cover enquiry ownership, operator
separation, source citations, foreign-source abstention and source removal.
The guide includes reproduction commands and functional/partial/interface-only
capabilities. This is a captured-image presentation; a live video recording is
not included. Hosted acceptance and release approval remain outstanding.

Phase exit: a reviewer can reproduce the demonstrated behavior from the guide.

## Later development for live business use

The next local development increment implements optional durable agent memory and
conversation consent using `AGENT_MEMORY_PATH`; see the
[verification and configuration record](../verification/durable-agent-memory-local-2026-11-26.md).
It does not add contact-wide consent, automatic migration, durable approvals or replay.

The following increment improves supplied-source question wording: bounded English
wrappers and listed inflection/spelling variants match without rewriting the quoted
source. See [verification and limits](../verification/supplied-question-wording-local-2026-11-26.md).
General semantic retrieval and translation remain future work.

The Knowledge page now adds agent-bound question sets, passage/no-answer checks,
local save/load and downloadable cited results. Expected answers never become
knowledge. See the [local evaluation record](../verification/agent-knowledge-evaluation-local-2026-11-26.md).
Shared server-side datasets and evaluation history remain future work.

All source import methods now expose optional review deadlines, including raw file
uploads. The page displays stored deadlines; expiry and explicit re-import renewal
pass locally for all 13 agents. See the
[review-date lifecycle record](../verification/source-review-dates-local-2026-11-26.md).
Scheduled review reminders remain future work.

Saved source text can now be read in the Knowledge page before review, with PDF page
numbers and organization/agent-scoped access. Previewing overdue material does not
restore it to answers. See the
[saved text preview record](../verification/saved-source-preview-local-2026-11-26.md).

The saved-text preview now supports explicit source review without re-upload. It
changes only the deadline and a fresh customer-approval choice, preserving content
and ownership. See the [renewal verification](../verification/saved-source-review-local-2026-11-26.md).
Source review history now records authenticated reviewers and previous/new values
atomically, with scoped older-page navigation. See the
[review-history verification](../verification/source-review-history-local-2026-11-26.md).
It covers explicit review actions and is removed with its source. Scheduled reminders and a
broader immutable audit/retention policy remain future work.

A manual selected-agent review queue now shows overdue and seven-day due sources,
using the server calendar and opening the existing review flow. See the
[queue verification](../verification/source-review-queue-local-2026-11-26.md).
It does not schedule notifications or change sources merely by checking dates.

Manual knowledge questions now support staff and customer audiences. Customer mode
quotes only current, approved own sources and explicitly abstains after approval
withdrawal; the dashboard verifies the result's audience. See the
[customer preview record](../verification/customer-knowledge-preview-local-2026-11-26.md).
Saved evaluation sets remain staff checks and no customer delivery is added.

Plan separate work for durable runtime storage and consent, scheduled follow-ups,
production authentication, sandbox provider validation, monitoring and recovery.
Voice/telephony, live calendar and partner property APIs require additional
implementation or authorized access. Better paraphrase retrieval needs independent
quality evaluations. These are not prerequisites for an accurately labelled
portfolio demonstration.
