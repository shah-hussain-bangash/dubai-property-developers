# Phase 1 agent boundary review

Local review on 26 November 2026 of candidate
`c517a6cb584d89975c9a51bf45435db9b0cb348c` in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The PR remains open and unmerged. This is the first review group in the
[completion guide](../development/portfolio-completion-guide.md), not sign-off
on the complete 136-file diff or the hosted environment.

## Scope and findings

Thirteen implementation files inspected locally matched the candidate's Git blob
hashes after line-ending normalization: agent base/context, tool gateway,
idempotency, memory interface, approval store, assigned-source store, document
search, email send, SQL conversation memory, source API, approval API and private
knowledge gateway.

No new confirmed blocker was found within this bounded review.

| Control | Reviewed behavior and evidence |
| --- | --- |
| Trusted identity | Agent runs reject principal/context organization mismatch. Tool calls take the agent ID and allowlist from the agent specification. Payload ownership cannot override these fields. |
| Source ownership | Source API operations use the authenticated principal's organization and a registered agent. Source lookup/deletion filters both owner fields. Read and modification permissions are separate. |
| Source-only answers | Answers consist of selected excerpts or the fixed no-answer response. Customer retrieval requires customer-approved, unexpired sources. |
| Approval and replay | Agent identity participates in action keys. The gateway checks organization, allowlists and permissions before execution/replay; approval execution retains the requesting agent. |
| Source withdrawal | Before a new source-backed send, current source ownership, approval, review date, title, passage reference and exact body/subject are checked. Completed cached sends replay without sending again. |
| Memory | Default memory partitions organization, agent and conversation identity. The SQL adapter filters organization/agent history and locks state updates; its runtime activation is unchanged. |

## Local test outcome

From the source root, using the existing project virtual environment:

```text
python -m pytest tests/security/test_agent_knowledge_isolation.py tests/security/test_assigned_source_api_isolation.py tests/security/test_agent_memory_isolation.py tests/security/test_agent_action_isolation.py tests/security/test_source_bound_approvals.py tests/security/test_source_review_deadline_preservation.py tests/security/test_delivery_key_isolation.py tests/security/test_explicit_delivery_consent.py tests/security/test_agent_source_format_journey.py tests/evaluations -q -p no:cacheprovider --basetemp=../phase1-boundary-review-20261126
```

Result: **159 passed**, zero failed/skipped/expected failures, in 12.60 seconds.
One existing Starlette TestClient/httpx deprecation warning was emitted.
The environment used Python 3.14; no PostgreSQL service or real provider was used
by this selected run. A repeat should use a fresh disposable basetemp directory.

The all-agent lifecycle case covers 13 agents and 39 PDF/Markdown/mock-website
sources, restart persistence, exact excerpts and PDF page citations, 468 cross-agent
abstentions, 39 cross-organization abstentions, hidden-content exclusion, foreign
deletion rejection and scoped removal. Website transport is mocked; PDF extraction
uses the actual subprocess. API isolation tests additionally cover pasted text.
Evaluation cases use fictional datasets. Mock sends exercise approvals without
contacting customers.

## Release conditions and remaining review

- Persisted old action keys/approvals need reconciliation before rollout. The tests
  do not migrate an existing external delivery ledger.
- Default conversation memory and consent remain process-local. These results do
  not establish recovery across restarts or contact-wide consent synchronization.
- The SQL adapter was inspected but not exercised against PostgreSQL in this local
  run. Existing CI integration evidence is separate.
- The private knowledge gateway promotes identities accepted by its original
  verifier for source management. Its owner-only guarantee therefore depends on
  the private deployment verifier and browser gateway; that private configuration
  was not exported or independently verified here. Confirm it before shared access.
- No check cancels an already in-flight provider operation after source withdrawal.
- Remaining review groups: external-action adapters, knowledge ingestion,
  dashboard controls and deployment/data compatibility. Full PR approval is pending.
- Hosted revision and eligible synthetic operator access remain unconfirmed.

Only review documentation changed. No application fix, merge, deployment, real CRM
write or outbound customer communication was performed.
