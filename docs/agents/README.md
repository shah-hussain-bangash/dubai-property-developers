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
| 11 | `marketing` | partial | none | Consent-filtered segmentation; copy drafts require approval. No sending |
| 12 | `documents` | partial | `documents.search` | Extractive summaries; cited answers; low confidence or stale sources go to a human |
| 13 | `analytics` | partial | `analytics.sales_summary` | Lead source/status/conversion + agent performance from execution records |

## Adding an agent

1. Create `agents/<name>/schemas.py` (input/output models) and `agents/<name>/agent.py`.
2. Define `spec = AgentSpec(...)` with an honest `implementation_status` and a minimal `allowed_tools`.
3. Implement `async def execute(self, data, ctx)`. Override `outcome_status` for approval/escalation.
4. Add the class to `AGENT_CLASSES` and add tests under `tests/agents/`.

## LLM usage

`deps.llm` (a `ModelRouter`) is available to every agent. No agent depends on it yet, because only the
mock provider exists. When adding LLM drafting, build prompts with `core/llm/prompts.build_messages`
so customer and document text stays in `<untrusted>` blocks. Keep the tool and approval checks as they
are: they don't depend on model output.
