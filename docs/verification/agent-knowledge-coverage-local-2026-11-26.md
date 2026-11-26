# All-agent source coverage overview

Verified locally on 26 November 2026 against parent
`c94094573353560b9d45dad755485784ec74f09a` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All fixtures are
fictional, providers are mocked and no live messages or CRM writes occurred.

## Behavior and limits

Knowledge now has a manual **Knowledge across your agents** overview. Check all
agents' sources loads counts for every registered agent, including empty agents,
using the authenticated organization's sources and the server calendar day.

- Saved: all sources, including overdue material.
- Current for staff: undated or dated today/later.
- Current customer-approved: current sources with explicit customer approval.
- Overdue: deadline before the checked day; excluded from answers.
- Due within seven days: today through seven days ahead, inclusive.
- Undated: no automatic date cutoff; included in current staff sources.

These categories overlap as described; due-soon/undated are not additional source
inventories. A customer-approved flag alone does not make overdue material eligible.
Counts describe source availability, not answer quality, evaluation results, agent
implementation status, model training or live provider readiness.

The private read-only `GET /api/v1/knowledge/agents/coverage` requires existing
knowledge-read permission. It reads only agent/deadline/approval metadata in one
organization-scoped SQL query, filters to the trusted runtime registry, and returns
no titles, source text, IDs, customer records or foreign organization data. An
empty registry yields an empty summary. Storage not configured returns 503.
Responses remain private/no-store. Checking never changes source data or review
history. Existing source/evaluation schemas and delivery permissions are unchanged.

The dashboard verifies the registry's exact agent order, calendar date, seven-day
window, bounded integer counts, category relationships and aggregate sums before
showing results. Open knowledge selects the corresponding existing agent editor
and clears the overview, including when selecting the current agent. Normal
agent-switch draft/approval clearing remains in force. Changes to saved sources
or agent selection remount/clear the overview and cancel pending requests. Failed
refreshes clear old counts; timeouts and errors offer another manual check.

The overview is fetched only when requested. Recheck after source changes, another
staff member's changes or a new server day. It is not a scheduler, notification or
saved historical report. This increment was verified through the real local API
and automated dashboard components; no new browser walkthrough is claimed.

## Reproduce

1. Start a disposable local API/dashboard with mock providers and persistent source
   storage. Sign in as a staff member with knowledge-read access. Open Knowledge;
   no overview request occurs automatically.
2. Choose Check all agents' sources. Empty agents show No sources assigned. Counts
   and the checked server day appear. The response includes all 13 registered
   agents, with no source contents or other organizations' records.
3. In a controlled source-store test calendar, prepare one approved source due today,
   one approved source imported yesterday and now overdue, and one undated staff
   source. Expected overall counts: three saved, two current for staff, one current
   customer-approved, one overdue, one due soon and one undated.
4. Open knowledge for an agent with overdue material. Its editor is selected and
   the overview clears. View its saved text and explicitly review it with a future
   date and customer approval. Recheck: overdue drops and current customer-approved
   increases. Explicit removal reduces saved count.
5. Advance only the source-store fixture calendar to the next day and restart the
   local API. The previously today-dated source becomes overdue and loses customer
   eligibility. Another organization's overview continues to show only its data.
6. Simulate a failed/slow overview request. Old counts disappear and a retry is
   available. Switching agents or changing sources cancels/discards stale requests.

[Structured API evidence](agent-knowledge-coverage-local-2026-11-26.json) records
initial, other-organization, renewed, removed and next-day/restart results. Only
explicit review/removal actions mutate records; overview reads leave them unchanged.

## Validation

- Three new API/storage tests cover all 13 agents with 65 own sources and 13 foreign
  sources, exact category boundaries, empty/unknown registry scopes, viewer/auth,
  restart, read-only state/history, explicit review and deletion refresh.
- Fifteen new dashboard cases cover deferred loading, empty agents, navigation and
  unsaved approval reset, disabled controls, error/retry, timeout, cancellation and
  rejected dates/owners/counts. The focused dashboard run passed 58 tests.
- Full backend: 2,513 passed, 156 skipped, four existing expected failures and
  662 passing subtests. Database integration services are provided separately in CI.
- Full dashboard: 1,070 passed across 103 files. Type checking and production
  compilation passed. Lint has zero errors and 27 existing warnings.
- Ruff, Python formatting and focused mypy passed. The local Windows build retains
  its existing standalone symlink packaging warning; it is not a release artifact.

No merge or deployment is included. Hosted acceptance remains dependent on hosting
access recovery; source counts do not resolve that dependency.
