# CRM account organization binding

Verified locally on 24 November 2026 against PR #87 revision
`be44e05b7d42cd404a3b8fb35cef6e3f3ffb0636` plus this change.

## Observed blocker

The runtime shares one configured EspoCRM client among its CRM tools. Gateway
organization checks validated caller identity, but did not establish which
organization owned that account. An authenticated caller from a different
organization could reach find, create, update and note operations on the same
client. The regression used mock methods only; all four were reachable before
the fix. No live CRM was contacted.

## Correction

All four runtime CRM tools bind their account to the configured
`DEFAULT_TENANT_ID`. Contextual calls require both the execution organization and
the principal organization to match that binding. Missing bindings fail closed.
Bound runtime tools also reject standalone execution without trusted identity.
Explicitly constructed unbound standalone adapters retain their internal legacy
interface; they cannot be invoked contextually without a binding.

An optional tool ownership authorization hook runs before gateway cache lookup
and approval creation, and before executing/replaying a stored approval. CRM
tools implement that hook and recheck it on direct contextual execution.
Denied gateway calls are audited. Existing approval IDs and cached results do
not override the binding. Execution permissions and agent allowlists remain in
force; agents may still request approvals without permission to execute them.

## Checks and reproduction

All **25 new regression cases passed**, covering all four methods, direct calls,
unbound contextual calls, spoofed principal/context identity, foreign pending
approval prevention, persisted foreign approvals, previously cached foreign
results, a non-default configured owner, and legacy standalone compatibility.
The owning workspace's fictional lead completed create, find, update and note
operations. No denied case called the CRM client. The focused CRM/gateway/agent
suite passed **62 tests**.

The full local Python 3.14 suite reported **1,684 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for four source files passed.

```text
python -m pytest tests/security/test_crm_account_binding.py tests/security/test_agent_action_isolation.py tests/unit/test_tool_gateway.py tests/unit/test_tool_gateway_tenant_scope.py -q
python -m pytest -q
python -m mypy tools/base.py tools/crm workflows/runtime.py
```

## Limits

This enforces a single-account organization binding, not separate CRM accounts
for multiple organizations. Additional organizations now receive authorization
errors until explicit account routing is implemented. Confirm `DEFAULT_TENANT_ID`
is the account's owner before rollout; changing that setting is an account
reassignment, not an automatic data migration. Historical CRM data reconciliation
and live EspoCRM verification remain outside this mock-only change. Direct
integration-client use by internal trusted code remains outside the tool boundary.
No live CRM writes, customer messages, merge or deployment occurred.
