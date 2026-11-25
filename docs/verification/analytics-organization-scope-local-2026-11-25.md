# Analytics organization boundaries

Verified locally on 25 November 2026 against PR #87 revision
`873b847306d2b1c494feb17ec03bf5d943d730a9` plus this change.

## Observed issue

Analytics summarized the runtime's global execution recorder, which lacked an
organization field. A report therefore combined run counts, status ratios and
durations from other organizations. Contextual lead aggregation also accepted
foreign or mixed-organization supplied leads. The recorder retained mutable
input/output dictionaries, allowing callers to alter recorded metadata.

## Change

Base-agent execution records now carry the authenticated principal's organization
on success, disabled, invalid-input, failure and timeout paths. All 13 agents
reject mismatched principal/context organizations before input validation or
execution; the denied attempt is attributed to the principal's organization,
rather than the organization it attempted to select.

The in-memory recorder owns deep snapshots and offers an organization-filtered
snapshot read. Analytics uses that read for agent performance. Records with no
known owner are excluded rather than assigned through correlation IDs or other
inference. Contextual sales aggregation checks both principal/context identity
and each supplied lead's organization; mixed inputs fail without a partial report.
Standalone aggregation retains its pure supplied-data interface and reads no
execution history. Role permissions and agent tool allowlists are unchanged.

## Verification

All **26 new regression cases passed**: mismatch rejection across all 13 agents,
trusted ownership on five record paths, independent reports for two organizations,
legacy-record exclusion, foreign/mixed lead rejection, direct contextual identity
checks, correct own counts/conversion with performance disabled, and detached
input/global/scoped recorder snapshots. The focused agent/analytics/memory suite
passed **62 tests**. The initial 25-case run exposed 24 failures and one passing
own-report control before the correction; a scoped-snapshot case was then added.

The full local Python 3.14 suite reported **1,753 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for ten base-agent, analytics-agent and analytics-tool source files passed.

```text
python -m pytest tests/security/test_analytics_organization_scope.py tests/agents/test_agents.py tests/security/test_agent_memory_isolation.py -q
python -m pytest -q
python -m mypy agents/base agents/analytics tools/analytics
```

## Limits

Execution history remains process-local with the existing shared bounded retention;
this does not add durable reporting, per-organization retention quotas, SQL-backed
analytics, or a historical ownership migration. Aggregate inputs are supplied
records, not a new CRM/database query. No customer messages, live CRM writes,
merge or deployment occurred.
