# Workflows

Each workflow is a `WorkflowDefinition` (`workflows/engine/core.py`). It has a typed Pydantic state and
ordered steps. A step returns one of:

- `continue`
- `complete`: success, skip the remaining steps
- `pending_approval`
- `escalate`

Step errors produce a `failed` run with a structured error. Every run records step names, outcomes and
durations.

The runner rejects mismatched principal/context organizations before state validation or any step.
The in-memory history store saves detached snapshots and returns detached diagnostic views;
changes require an explicit save. A retained execution ID cannot change its organization or workflow
identity. See the [workflow history verification](../verification/workflow-history-ownership-local-2026-11-25.md).

| id | Steps | Status | Terminal outcomes |
|---|---|---|---|
| `lead_processing` | validate_normalize_deduplicate → duplicate_gate → qualify → route → store_in_crm | functional | succeeded (duplicates end at the gate), pending_approval if CRM writes need approval |
| `property_recommendation` | search_filter_rank → compliance_check | functional | succeeded. Fails if a recommendation lacks the ROI/demo disclaimers |
| `sales_conversation` | detect_intent → retrieve_context_and_draft → approve_and_dispatch | partial | escalated (complaint, unsubscribe, injection, no cited source) or pending_approval |
| `followup_automation` | check_prepare_request_approval | partial | pending_approval per send. Escalated for overdue or max-attempt items |
| `crm_sync` | validate → match_and_resolve_conflicts → compute_update → audit | partial | escalated on conflict or delete. Does not persist yet |
| `knowledge_support` | retrieve_and_prepare_cited_answer → confidence_evaluation | partial | pending_approval (customer answer) or escalated (low confidence or stale source) |
| `lead_requalification` | qualify_and_route | functional | sub-flow |

After a human approves, `POST /api/v1/approvals/{id}/decision` executes the stored action through
`ToolGateway.execute_approved` under the approver's permissions. The idempotency key prevents
duplicate sends.
