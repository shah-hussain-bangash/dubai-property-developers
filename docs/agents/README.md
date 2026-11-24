# Agents

All agents subclass `BaseAgent` (`agents/base/agent.py`) and are registered in `agents/registry.py`.
`BaseAgent.run()` provides input validation, the timeout (`AGENT_DEFAULT_TIMEOUT_SECONDS` or a per-agent
`AgentConfig`), tracing spans, structured logs, error mapping to `AgentResult`, and execution records.
Agents reach external systems only through tools on their `allowed_tools` allowlist.

Result statuses: `succeeded`, `failed`, `timed_out`, `pending_approval`, `escalated`.

| # | agent_id | Status | Allowed tools | Notes |
|---|---|---|---|---|
| 01 | `supervisor` | functional | none | Routing table + keyword intent; escalates complaints, unsubscribes and suspected injection. Plans only; the workflow engine executes |
| 02 | `lead_intake` | functional | `search.lead_duplicates` | Sanitization, E.164 phone normalization (default region AE), email/location normalization, hashed dedupe keys |
| 03 | `qualification` | functional | `analytics.score_lead` | `rules-v1` explainable score; categories hot/warm/nurture/cold; rent goes to the leasing queue. Weights are uncalibrated |
| 04 | `property_recommendation` | functional | `property.match`, `property.search` | Hard filters + weighted ranking with reasons and caveats; fictional catalog |
| 05 | `sales_conversation` | partial | `documents.search` | Intent → public-document retrieval → approved template draft (EN; basic AR) → always approval-gated; escalates when no current cited source exists |
| 06 | `followup` | partial | `email.render_template`, `email.send`, `whatsapp.send_message` | Due/consent/status checks, max 3 attempts, 48h overdue escalation, approval-gated dispatch |
| 07 | `crm` | functional | `crm.*`, `leads.save` | Local save + EspoCRM upsert (mock) + qualification note. Opportunities pending |
| 08 | `email` | partial | `email.render_template`, `email.send` | Template drafts, approval-gated send, rule-based reply classification. No email provider configured |
| 09 | `whatsapp` | partial | `whatsapp.send_message` | Opt-in, 24h window (free text vs template), opt-out handling, Meta webhook parser |
| 10 | `voice` | interface_only | none | Audio raises `integration_not_configured`; a transcript-only path exists for contract tests; always escalates |
| 11 | `marketing` | partial | `documents.search` | Consent-filtered segments; supplied-source drafts quote only approved own material, otherwise escalate. No sending |
| 12 | `documents` | partial | `documents.search` | Extractive summaries; cited answers; low confidence or stale sources go to a human |
| 13 | `analytics` | partial | `analytics.sales_summary` | Lead source/status/conversion + agent performance from execution records |

## Adding an agent

1. Create `agents/<name>/schemas.py` (input/output models) and `agents/<name>/agent.py`.
2. Define `spec = AgentSpec(...)` with an honest `implementation_status` and a minimal `allowed_tools`.
3. Implement `async def execute(self, data, ctx)`. Override `outcome_status` for approval/escalation.
4. Add the class to `AGENT_CLASSES` and add tests under `tests/agents/`.

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

This workspace uses only supplied sources, with no model generation, demo facts or web-search
fallback. It returns matching quoted passages rather than a synthesized answer. The lexical search
can miss paraphrases; reword the question or add a clearer source. Instructions inside a document
are quoted data and cannot grant tools or trigger actions. Answers are staff previews and send
nothing to customers. Voice and other partial provider capabilities are unchanged.

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
Conversation history and explicitly passed workflow records remain separate concerns; this change
does not claim isolation of every runtime store.

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
