# Agent-owned approvals, replays and provider keys

Verified locally on 24 November 2026 against PR #87 revision
`387db0c2e4cbb14cdef07c5338ecfc1cc3af01c3` plus this change.

## Confirmed gap

Action keys included organization, tool and payload, but omitted the trusted agent
identity. Equal payloads from different agents (or an unscoped staff caller) could
share a pending approval, execute using another agent's approved request, or
receive a cached result before current source ownership was checked. A copied
source-backed email/WhatsApp payload demonstrably returned `replayed` to Follow-Up
instead of requesting a separate approval. This did not expose source text that
the caller had not already supplied, but it bypassed the agent-owned action
lifecycle. All 18 initial regressions failed on the prior revision.

## Correction

The existing key helper accepts a keyword-only trusted `agent_id`. Agent keys
hash a structured organization/agent/tool/payload tuple. Gateway approvals,
execution locks and replay caches use that identity. Contextual email and
WhatsApp provider keys use the same boundary. Caller-supplied `agent_id` fields
cannot select the owner, and approved execution retains the original requesting
agent. Unscoped calls keep the pre-change namespace; standalone explicit delivery
keys remain compatible.

The existing payload-snapshot assertions now include trusted agent identity. The
cross-gateway concurrency fixture now uses the same trusted agent for direct and
approved entry points; all four combinations still prove a single execution and
a cached replay. It no longer treats an unscoped staff action as the same action
as an agent request. Actual agent allowlists and capabilities are unchanged.

## Validation

All **21 new cases passed**: independent approvals for all 13 agent identities
using a synthetic tool context, pending/approved/completed lifecycle separation,
copied source-backed payloads rejected at new execution, agent-separated provider
keys, stable same-agent provider retries, and a fixed pre-change unscoped cache
key. The focused gateway/source/consent/delivery suite passed **119 tests**.

The full local Python 3.14 suite passed **1,659 tests**, with **155 skips**, **four
existing expected failures**, **662 passing subtests** and three existing
dependency/configuration warnings. Integration skips require explicitly enabled
services; expected failures cover existing recovery/fencing gaps. Ruff, formatting
checks and mypy for nine source files passed.

Reproduce with development dependencies:

```text
python -m pytest tests/security/test_agent_action_isolation.py tests/security/test_delivery_key_isolation.py tests/unit/test_tool_gateway_payload_snapshots.py tests/unit/test_tool_gateway_cross_gateway_concurrency.py -q
python -m pytest -q
python -m mypy core/resilience/idempotency.py tools/base.py tools/email tools/whatsapp
```

## Limits

This verifies local mock deliveries, not live-provider deduplication or distributed
exactly-once execution. Agent-scoped key values intentionally change; any deployment
with persisted in-flight/completed agent actions needs a reconciliation plan before
rollout. This change does not migrate an external delivery ledger. Stored approval
IDs retain their original key and requesting identity. No live messages, CRM writes,
merge or deployment occurred.
