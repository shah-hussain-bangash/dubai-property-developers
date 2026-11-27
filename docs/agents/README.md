# Agents

All agents subclass `BaseAgent` (`agents/base/agent.py`) and are registered in `agents/registry.py`.
`BaseAgent.run()` provides input validation, the timeout (`AGENT_DEFAULT_TIMEOUT_SECONDS` or a per-agent
`AgentConfig`), tracing spans, structured logs, error mapping to `AgentResult`, and execution records.
Agents reach external systems only through tools on their `allowed_tools` allowlist.

Result statuses: `succeeded`, `failed`, `timed_out`, `pending_approval`, `escalated`.

Execution records carry the authenticated principal's organization. Agent runs reject mismatched
principal/context organizations before input validation or execution. Analytics reads only its
organization's owned execution records and rejects foreign lead inputs. Legacy records without
ownership are excluded. See the [analytics scope verification](../verification/analytics-organization-scope-local-2026-11-25.md).

Marketing batches and contextual qualification scoring also require supplied lead organizations to
match the trusted caller. Mixed batches fail before segmentation or knowledge lookup, including
foreign leads without marketing consent. See the [lead planning verification](../verification/lead-planning-ownership-local-2026-11-25.md).

| # | agent_id | Status | Allowed tools | Notes |
|---|---|---|---|---|
| 01 | `supervisor` | functional | none | Routing table + keyword intent; escalates complaints, unsubscribes and suspected injection. Plans only; the workflow engine executes |
| 02 | `lead_intake` | functional | `search.lead_duplicates` | Sanitization, E.164 phone normalization (default region AE), email/location normalization, hashed dedupe keys |
| 03 | `qualification` | functional | `analytics.score_lead` | `rules-v1` explainable score; categories hot/warm/nurture/cold; rent goes to the leasing queue. Weights are uncalibrated |
| 04 | `property_recommendation` | functional | `property.match`, `property.search` | Hard filters + weighted ranking with reasons and caveats; fictional catalog |
| 05 | `sales_conversation` | partial | `documents.search` | Intent → public-document retrieval → approved template draft (EN; basic AR) → always approval-gated; escalates when no current cited source exists |
| 06 | `followup` | partial | `documents.search`, `email.render_template`, `email.send`, `whatsapp.send_message` | Own-source drafts in supplied mode; due/consent/reply/attempt checks and approval-gated dispatch |
| 07 | `crm` | functional | `crm.*`, `leads.save` | Local save + EspoCRM upsert (mock) + qualification note. Opportunities pending |
| 08 | `email` | partial | `documents.search`, `email.render_template`, `email.send` | Own-source cited drafts in supplied mode, approval-gated send requests, reply classification. Mock sender |
| 09 | `whatsapp` | partial | `documents.search`, `whatsapp.send_message` | Own-source cited replies, opt-in/opt-out and 24h-window checks. Supplied mode escalates outside window; mock client |
| 10 | `voice` | interface_only | none | Audio raises `integration_not_configured`; a transcript-only path exists for contract tests; always escalates |
| 11 | `marketing` | partial | `documents.search` | Consent-filtered segments; supplied-source drafts quote only approved own material, otherwise escalate. No sending |
| 12 | `documents` | partial | `documents.search` | Supplied-source summaries and answers use cited own passages; missing/stale evidence goes to a human |
| 13 | `analytics` | partial | `analytics.sales_summary` | Lead source/status/conversion + agent performance from execution records |

The runtime's single CRM account is bound to `DEFAULT_TENANT_ID`, for mock and HTTP clients.
CRM tools reject other organizations before approval creation, cached replay or client access;
human approval cannot override the account binding. Additional organizations need their own
explicit account routing before CRM synchronization is supported. This does not provision accounts
or verify live EspoCRM. See the [CRM binding verification](../verification/crm-account-binding-local-2026-11-24.md).

The runtime calendar follows the same `DEFAULT_TENANT_ID` account binding. Bookings require
explicit UTC offsets, and provider keys retain the trusted organization/agent and complete
approved event. The calendar remains mock-only; no existing agent gains booking permission.
See the [calendar boundary verification](../verification/calendar-booking-boundaries-local-2026-11-24.md).

## Adding an agent

1. Create `agents/<name>/schemas.py` (input/output models) and `agents/<name>/agent.py`.
2. Define `spec = AgentSpec(...)` with an honest `implementation_status` and a minimal `allowed_tools`.
3. Implement `async def execute(self, data, ctx)`. Override `outcome_status` for approval/escalation.
4. Add the class to `AGENT_CLASSES` and add tests under `tests/agents/`.

Use `self.conversation_memory(ctx)` for agent history/state rather than the raw dependency store.
It binds the organization and agent from trusted execution context, independently of payload IDs.

## LLM usage

`deps.llm` (a `ModelRouter`) is available to every agent. These 13 agents currently use deterministic
rules, templates and extractive retrieval; they do not call a model or learn from examples at runtime.
The router defaults to a mock and has optional OpenAI and local Ollama adapters requiring explicit
configuration. When adding LLM drafting, build prompts with `core/llm/prompts.build_messages`
so customer and document text stays in `<untrusted>` blocks. Keep the tool and approval checks as they
are: they don't depend on model output.

## Separate agent knowledge and evaluations

### Upload your own knowledge

Open **Knowledge** in the signed-in operations workspace. Select an agent, then add a PDF, text or
Markdown file, a public HTTPS page, or pasted text. Sources are assigned to that agent and your
organization only. Use **Test this agent's knowledge** to see exact matching excerpts, source titles
and PDF page references. Missing or unrelated knowledge produces an explicit not-found response.
Sources can be removed from future answers after confirmation.

Text imports accept UTF-8 and BOM-marked UTF-16/UTF-32. Unreadable bytes are rejected rather than
silently replaced. Save unsupported files as UTF-8 or paste their text; see the
[text encoding verification](../verification/knowledge-text-encoding-local-2026-11-25.md).

This workspace uses only supplied sources, with no model generation, demo facts or web-search
fallback. It returns matching quoted passages rather than a synthesized answer. The lexical search
can miss paraphrases; reword the question or add a clearer source. Instructions inside a document
are quoted data and cannot grant tools or trigger actions. Answers are staff previews and send
nothing to customers. Voice and other partial provider capabilities are unchanged.

Supplied-source matching now ignores a small set of leading English question wrappers such as
“Please tell me about” and “Could you explain”, and recognizes explicitly listed domain word forms
such as payment/payments, booking/bookings and instalment/installment. This is bounded lexical
normalization, not general paraphrase understanding or translation. The overlap thresholds remain
the same, and answers/citations retain the original wording. No source re-import or hashing-vector
rebuild is needed. See the [question wording verification](../verification/supplied-question-wording-local-2026-11-26.md).

Supplied-source matching recognizes Unicode letters/numbers and canonical spellings while keeping
the original excerpts unchanged. Punctuation alone cannot match a source. This adds no translation,
stemming or CJK word segmentation; the legacy vector/hash tokenizer stays unchanged. See the
[Unicode source matching verification](../verification/unicode-source-matching-local-2026-11-25.md).

By default, sources are **staff only**. Check **Allow this source in customer-facing answers** only
for approved public material. In supplied-source mode, document and sales-conversation agents search
only their own assigned, customer-approved sources for customer replies; an empty corpus never
falls back to fictional fixtures. Sales replies quote the supplied material without appending
template facts. Their existing approval and escalation controls remain in place. Routing,
calculations and other deterministic agents still use typed workflow inputs; uploading a policy
does not retrain them or silently change their rules.
Marketing campaign drafts also search only the Marketing Agent's own customer-approved sources,
using the campaign goal as the query. The headline uses the source title and the body quotes cited
passages without template claims. Missing, unrelated, removed or unapproved sources produce no
draft and request human review. Marketing consent remains required; this agent cannot send.
Email drafts in supplied-source mode require a `knowledge_query` (3–1,000 characters).
They use the Email Agent's own customer-approved sources for the subject/title and cited body;
an absent query or source requests human review without a template fallback. For example,
`{"mode":"draft","knowledge_query":"approved garden policy"}` is a draft-only agent input.
Inbound email classification remains independent of source retrieval. Existing send requests
retain approval and marketing-consent checks.

Inside the WhatsApp service window, supplied-source replies search the WhatsApp Agent's own
customer-approved sources using the incoming message. An unverified `draft_reply` is ignored.
Outside the service window, no generic provider template is substituted: the result requests
staff review because approved template content/catalogue sync is not configured. Consent,
opt-out, complaints and send-approval checks still apply. This does not configure live messaging
providers.

Follow-Up schedules compare times in UTC. Legacy timestamps without an offset mean UTC, rather than the
host's local timezone; new integrations should send explicit offsets. Supplied task models are
not rewritten. See the [follow-up timezone verification](../verification/followup-schedule-timezones-local-2026-11-25.md).

Follow-Up Agent tasks in supplied-source mode also require their own `knowledge_query`
(3–1,000 characters). Follow-up drafts quote only customer-approved sources assigned to the
Follow-Up Agent, without borrowing Email or WhatsApp sources. Missing queries or relevant
sources escalate that task without an action; other grounded tasks in the batch can proceed.
Email subjects use source titles. WhatsApp follow-ups use cited free text only inside the
current service window; outside it they request staff review. Their action has `template: null`
and source citations. Due/status/reply/consent/attempt checks and send approvals remain in place.
The database task source and scheduled worker trigger remain partial; adding knowledge does not
activate scheduling or live messaging. Developer fixture mode retains its template workflow.

The shared WhatsApp free-text window requires a non-future inbound timestamp no more than
24 hours old. Invalid timestamp strings/types produce validation errors before send approval;
missing timestamps cannot authorize free text. Time-zone offsets are handled consistently, with
legacy naive datetime values interpreted as UTC. See the
[timestamp guard verification](../verification/whatsapp-timestamp-guards-local-2026-11-24.md).

The send tool revalidates these rules immediately before the provider call, after execution-lock
waits and asynchronous source verification. Passing an earlier check or having an approved draft
does not preserve an expired window. See the
[execution-window regressions](../verification/whatsapp-execution-window-local-2026-11-24.md).

Source-only send requests retain their citation snapshot in the private approval payload.
Immediately before a new provider call, the send tool rechecks the original agent and organization,
current customer approval/review date, source title, passage reference and exact outgoing text.
Email subjects must still match the cited source title. Removed, expired, withdrawn, renamed or
altered material blocks execution and requires a fresh draft/review. A human approval does not
override the source-only policy. Unscoped legacy approvals without citations cannot execute in this
mode; payload fields cannot supply their own trusted agent identity. Citation metadata stays inside
the approval system and is not passed to message providers.

Cached successful executions can still return their result after source withdrawal without
sending again. This check cannot recall messages already delivered or guarantee cancellation of
a provider request already in flight. It validates current sources immediately before calling the
provider; it does not hold a database lock across network delivery. See the
[approval-source verification](../verification/source-bound-approvals-local-2026-11-24.md).

Contextual email and WhatsApp sends derive provider delivery keys from the trusted organization,
tool action and complete approved payload. Identical event IDs in different organizations no
longer share a WhatsApp deduplication key. Changing an approved recipient/content produces a
different key, while retrying the same scoped payload retains its key. Email sends through the
gateway also receive non-empty keys when the caller did not supply one. Keys are opaque digests
instead of raw conversation IDs or addresses. Standalone calls without context retain their
explicit legacy key behavior. Provider-side deduplication still depends on the provider/client;
this does not establish distributed or live-provider exactly-once delivery. See the
[delivery-key verification](../verification/delivery-key-isolation-local-2026-11-24.md).

Document summaries in supplied-source mode require a `query`, just like document answers.
For example, `{"action":"summarize","query":"garden policy","max_sentences":3}` summarizes
matched passages from the Document Agent's own sources and retains their citations. Caller-supplied
`text` is ignored in this mode; import that text as an assigned source first. Customer summaries
require customer-approved sources; `audience: "staff"` can summarize that agent's own staff material.
Missing or unavailable evidence requests human review without a summary. This is a summary of
retrieved passages, not a full-document or whole-PDF synopsis. Developer fixture mode retains direct
text summaries. See the [summary verification](../verification/document-summary-supplied-source-local-2026-11-24.md).
Supplied-source mode also disables fictional corpus ingestion and the backend's seeded property
catalog. PDF text is not silently converted into verified structured property listings; use the
source-answer workspace to query it, and create reviewed property records separately.

Local setup uses `AGENT_KNOWLEDGE_PATH=.data/agent-knowledge/sources.sqlite3` from `.env.example`.
The Docker Compose API and worker share a dedicated `agent-knowledge-data` volume. Both images
prepare that directory for the non-root runtime user. Back up this private volume separately from
the browser portal and PostgreSQL data; do not commit it. Without the setting, source management
reports storage unavailable and explicitly labelled developer fixtures remain available for tests.
Supply a writable persistent path when starting the API outside Compose. Normal API authentication
is required: knowledge-read roles may preview answers; workflow-execution roles may import/remove
sources. The browser gateway continues to require the owner session.

Import limits are 2 MB per file/page response, 100 PDF pages, 200,000 extracted characters per source,
and 100 sources / 2,000,000 characters per agent and organization. PDFs run in a separate parser
process with a 15-second lifetime and Unix CPU/memory caps. Encrypted, malformed or image-only PDFs
need conversion/OCR before upload. Website imports pin a checked public IP, verify TLS, recheck
redirects and reject private-network targets. They import one readable page snapshot, without
JavaScript rendering, sign-in, cookies or recursive crawling. Review web snapshots as they age;
remove an obsolete source before importing its replacement so contradictory copies do not remain.
The API also supports an optional source `review_by` date; expired sources cannot supply answers.
Re-importing an identical source with an omitted or null date preserves its existing deadline.
Renew a dated source with an explicit valid replacement date; a null value does not clear it.
See the [review deadline verification](../verification/source-review-deadline-local-2026-11-25.md).

Source endpoints are under `/api/v1/knowledge/agents`: list agents; list/import sources at
`/{agent}/sources`; remove `/{agent}/sources/{source_id}`; and preview an answer at `/{agent}/answer`.
Imports accept JSON `{title, kind: "text", text}` or `{title, kind: "website", url}`, with optional
`customer_safe` and `review_by`. File imports use raw PDF/text/Markdown bytes with the corresponding
Content-Type and a `title` query parameter. Original binary files are not retained; extracted text,
source URL/title, ownership, import time and approval classification persist in SQLite.

### Fictional evaluation datasets

Every registered agent has its own versioned fictional dataset in
[`knowledge/agent_data/data`](../../knowledge/agent_data/data). Each file has:

- An agent owner and dataset version, validated against its filename.
- Role-specific knowledge entries with access levels, permitted roles and source review dates.
- At least three held-out behavioral cases: typed input, expected result status, selected output
  assertions and, where appropriate, an expected error. Cases include consent, approval, escalation
  or validation boundaries as well as ordinary behavior.

These are knowledge and evaluation data, **not separately fine-tuned models**. The evaluation inputs
and expected answers are never ingested into the knowledge store. Rules-based agents continue to
use their structured inputs and existing tool allowlists; adding a knowledge file grants no new
tools or outbound access. Their dataset examples exercise those inputs directly.

The registry validates all 13 datasets at startup. Development/test initialization ingests only
their knowledge entries and labels each chunk with its agent owner. `documents.search` receives
identity from the ToolGateway's trusted caller context; a payload cannot choose another agent,
organization or privileged role. Agent searches require their own owner label and retain tenant,
customer/staff, role and staleness controls. General unscoped retrieval remains available to
internal non-agent callers, and cannot see agent-owned chunks. The in-memory and pgvector search
paths apply the same `RetrievalFilter` ownership rule. Production does not auto-ingest fictional data.

Some public fictional FAQs are deliberately copied into both the sales-conversation and documents
datasets because both roles need them. The copies have separate agent-owned document keys and
retain their original review dates. Sharing a fact does not grant access to the other agent's corpus.
Conversation history/state now use the organization and agent scopes described below. Explicitly
passed workflow records and other runtime stores retain their own access rules; this does not
claim isolation of every store or automatically change workflow sharing.

### Agent conversation memory

`BaseAgent.conversation_memory(ctx)` provides an organization/agent-scoped view. A mismatched
principal/organization or a backend without scoped-memory support is rejected before memory use.
Sales Conversation and WhatsApp use this view for their history/state. Matching conversation IDs
in different organizations or agents cannot select the same memory; matching operators within
one organization/agent retain that conversation's state, including a WhatsApp opt-out.

Without `AGENT_MEMORY_PATH`, runtime memory is process-local. Set a writable private SQLite file
path to retain conversation history/state, including WhatsApp conversation opt-outs, across runtime
restarts. The example environment uses `.data/agent-memory/memory.sqlite3`; Compose API and worker
share a separate `agent-memory-data` volume. Scoped keys encode the full organization/agent/
conversation tuple unambiguously. SQLite patches serialize read/merge/write transactions across
connections. Existing in-memory state is not migrated, and there is no unscoped fallback or CRM
consent synchronization. See [durable memory verification](../verification/durable-agent-memory-local-2026-11-26.md).

The optional SQL adapter also supports scoped views without changing conversation UUIDs or adding
tables. It filters message history by organization and trusted agent ownership, ignores caller
ownership tags, and partitions state within existing JSON fields. State updates lock the row and
preserve other agent partitions. Unscoped callers do not receive agent-owned history/state and
cannot forge or replace reserved partitions. Legacy SQL state without agent ownership requires
explicit ownership review before scoped access; no automatic consent/state migration occurs.
The SQL adapter is not newly wired into runtime configuration by this change. See the
[memory isolation verification](../verification/agent-memory-isolation-local-2026-11-24.md).

WhatsApp changes conversation state with `update_state`, an atomic top-level patch rather than
a read/replace cycle. Ordinary messages update their inbound/contact/consent fields without
clearing an existing `opted_out` flag. In-memory patches are atomic on the local event loop;
SQL patches lock the conversation row; SQLite patches use an immediate transaction. Both preserve
other state fields within their scope.

WhatsApp Agent send approvals also carry their conversation reference. Before a new provider call,
the configured send tool checks that this organization's WhatsApp conversation still permits
replies and still matches the approved recipient. An opt-out, withdrawn consent flag, unknown
reference or recipient change blocks the queued send. Older requests without a reference need a
fresh draft. Completed cached sends can replay without delivering again. The reference is kept
inside the approval payload rather than added as a provider message field.

This is a per-conversation WhatsApp Agent check. It does not add a durable contact-wide consent
registry, automatic re-consent or CRM writes, and Follow-Up still relies on its typed workflow
consent input. Memory remains process-local by default, and an in-flight provider request cannot
be recalled. See the [opt-out concurrency verification](../verification/whatsapp-optout-concurrency-local-2026-11-24.md).

Run the agent and data-boundary checks without live providers:

```text
python -m pytest tests/agents tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/evaluations -q
```

The suite runs 39 per-agent dataset cases and checks all 13 knowledge scopes, payload spoofing,
tenant and role boundaries, unchanged tool allowlists, source review dates and detached dataset
copies. Passing voice cases means unsupported audio fails clearly and transcripts escalate; it
does not mean speech-to-text or calling is implemented. The functional/partial/interface statuses
in the table above remain the capability boundary.

The authenticated supplied-source API checks also cover every agent in two organizations,
persistence after restart, foreign-source deletion attempts, viewer restrictions and deletion
of identical content without removing another owner's copy. See the
[local verification record](../verification/agent-source-boundaries-local-2026-11-24.md).

When adding an agent, add its dataset and update the registry together. Keep input examples fictional,
make expected outcomes independent of current outputs, retain source provenance and review dates,
and add held-out cases when fixing an observed failure. Never add customer records or credentials.

The Knowledge page's Saved checks section supports a separate local question file for each
agent. Save the set before switching agents; load it later to rerun up to 20 expected-passage
or no-answer checks. Questions and expected passages are never added to source knowledge.
Results include actual source quotes and citations. These are staff-controlled retrieval checks, with staff and customer audiences;
no customer delivery or model training occurs. See the
[evaluation workspace verification](../verification/agent-knowledge-evaluation-local-2026-11-26.md)
for a complete fictional reproduction, limits and downloadable evidence.

Every Knowledge import method also accepts an optional Review by date. Saved sources show
their deadlines. They remain eligible through that server calendar day and stop contributing
afterward. Record a review from the saved-text preview or re-import with an explicitly reviewed
new date to renew material; leaving the import date
blank preserves the existing deadline for identical content. Editing the draft date clears
customer approval. Undated sources have no automatic date cutoff. See the
[review-date verification](../verification/source-review-dates-local-2026-11-26.md).

Use View saved text on a source to read its saved extraction and PDF page numbers before
reviewing it. This staff preview includes overdue material but changes neither deadlines
nor customer approval. It does not open the original file or refresh a website snapshot.
See the [saved text verification](../verification/saved-source-preview-local-2026-11-26.md).

Record a source review requires a new date and explicit review confirmation. Customer approval
starts unchecked on every review; saving resets the source to staff-only unless customer use is
explicitly selected. Source content and ownership are preserved. See the
[existing-source renewal record](../verification/saved-source-review-local-2026-11-26.md).

Load Source review history from the saved-text preview to see authenticated reviewers,
recording times and previous/new date and approval values. Older pages contain up to 20
reviews each. Review updates and history commit together. This covers explicit reviews,
not imports or all source mutations; deleting a source also deletes its history, as the
confirmation explains. See the [history verification](../verification/source-review-history-local-2026-11-26.md).

Use Sources needing review → Check review dates for a manual, selected-agent queue.
The server classifies overdue sources and those due today through seven days ahead;
current and undated sources are counted separately. Review source opens the saved
text and existing review form. Recheck after changes; this is not a scheduled
notification. See the [queue verification](../verification/source-review-queue-local-2026-11-26.md).

The manual question test also offers Preview audience. Staff includes all current assigned
sources; Customer includes only current, explicitly customer-approved own sources. The page
verifies the customer audience marker and exact citations before showing the result. Both
modes are previews and send nothing. Audience changes clear the old answer; agent changes
reset to staff. Saved checks have an independent audience selector. See the
[customer preview verification](../verification/customer-knowledge-preview-local-2026-11-26.md).

Saved checks now also support Customer mode and retain that choice in local question
files. Customer runs use only current approved own sources. Both the report and every
answer must identify the customer audience before the page shows the results. Older
files load as staff; changing audience clears results, and agent changes reset to
staff. Re-run after approval or deadline changes. See the
[customer evaluation record](../verification/customer-knowledge-evaluation-local-2026-11-26.md).

The Knowledge page now offers an on-demand organization-wide agent source overview,
including empty agents, current staff/customer-approved counts, overdue and seven-day
due counts, with navigation to each agent's existing editor. Counts measure source
availability, not answer quality or live feature readiness. Recheck after changes;
no scheduled notification is added. See the
[coverage verification](../verification/agent-knowledge-coverage-local-2026-11-26.md).

Saved sources also supports Download saved knowledge for one selected agent. The
private JSON copy preserves extracted text, PDF pages and source metadata, including
staff-only and overdue material. It excludes original files, review history and
question sets, changes no saved source state and is not an automatic restore or
complete database backup. See the
[saved-text export record](../verification/agent-source-export-local-2026-11-26.md).

Saved question files now preserve their original check IDs through load, edits,
runs and result downloads. Added questions receive a currently unused reference;
other checks are not renumbered. To recover references lost in an older download, load the original question
file again. See the
[traceability fix and reproduction](../verification/stable-knowledge-check-ids-local-2026-11-26.md).

If an agent's initial source list fails or times out, use Refresh sources. Knowledge
actions stay disabled until a successful owned list is loaded; a 45-second initial
load deadline makes the read retry available, and stale responses are discarded.
See the [loading recovery record](../verification/knowledge-source-load-recovery-local-2026-11-26.md).

If the workspace agent list fails or stalls, Retry knowledge workspace reloads that
read in place after an error or 45-second deadline. Invalid or stale registry
responses are not applied, and a valid empty registry has its own status. Source
readiness still gates all knowledge actions. See the
[workspace loading record](../verification/knowledge-workspace-load-recovery-local-2026-11-26.md).

Source lists are now checked before application, so malformed successful responses
cannot replace the last valid list or crash the editor. Initial failures keep
knowledge actions disabled; an invalid refresh after an acknowledged save retains
its success notice and permits a read retry. See the
[source-list recovery record](../verification/knowledge-source-list-validation-local-2026-11-27.md).

Source saves now require the existing selected-agent saved-source acknowledgement
before clearing drafts or showing success. Unconfirmed outcomes retain the draft
and request a source-list refresh before another import; a save may already have
committed. See the
[save acknowledgement record](../verification/knowledge-save-acknowledgement-local-2026-11-27.md).

Source removal now requires the existing boolean removed acknowledgement before the
page claims success. Unconfirmed outcomes retain the last known list, close the
confirmation and request read-only refresh before another attempt; the deletion may
already have committed. See the
[removal acknowledgement record](../verification/knowledge-removal-acknowledgement-local-2026-11-27.md).

In a saved-source review, withdrawing review confirmation now clears the draft's
customer approval. Reconfirm review and explicitly select customer use again if
needed; toggling the form alone does not revoke an existing stored approval. See the
[review confirmation record](../verification/knowledge-review-confirmation-local-2026-11-27.md).

Saved evaluation question files now share a 256 KB save/load budget, so a valid
20-case multilingual set can reload its own download. The existing case/field and
ownership/audience checks remain; source-upload limits are unchanged. See the
[question-file size record](../verification/knowledge-question-file-size-local-2026-11-27.md).

Main knowledge operations now release their UI wait at the 45-second deadline even
when a read ignores cancellation. Refresh sources before retrying; late abandoned
results cannot alter the recovered view. Server processing may still finish and
writes are not automatically repeated. See the
[operation timeout record](../verification/knowledge-operation-timeout-local-2026-11-27.md).
