# Customer audience for saved knowledge checks

Verified locally on 26 November 2026 against parent
`a9384d0aef2d05913cedc347a44f3199dcfa3f0c` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Evidence uses only
fictional sources and mock providers. There were no customer deliveries or live writes.

## Behavior and compatibility

Saved checks now have their own Staff/Customer audience selector. Customer checks
use only current, explicitly approved sources belonging to the authenticated
organization and selected agent. Expected passages remain evaluation data and never
enter retrieval. Questions, expectations and actual quoted citations are included
in downloadable results. Question files retain the customer audience on save/load;
customer downloads include `-customer` in the filename.

`POST /api/v1/knowledge/agents/{agent}/evaluate` accepts an optional top-level
`audience: "staff" | "customer"`. Omission defaults to staff. Existing staff files,
requests and response shapes continue to work. Invalid audiences are rejected.
Customer reports and every contained answer carry `audience: "customer"`; the
page verifies both levels, counts, per-case outcomes and exact cited answer text.
Missing, wrong or mixed audience markers are rejected before rendering a result.

Audience changes clear results while retaining questions. Agent changes reset the
question editor and audience to staff. Loading an older file explicitly restores
staff mode. Source changes clear displayed results. During a request, audience and
agent selection remain locked. The manual question preview has an independent
selector; changing one does not silently change the other's mode.

This adds authenticated staff-controlled evaluation, not public chat, model training,
customer delivery, server-side dataset storage or saved run history. All existing
read permissions, source ownership, no-store responses and the 20-case limit remain.
A run checks current retrieval behavior; it is not future delivery authorization or
proof of factual accuracy. Source review history is unaffected by evaluation.
Deploy matching API/dashboard versions together only after separate release approval.

## Reproduce with fictional data

1. In a disposable local mock-provider environment, select Document Agent. Add
   `Fictional publicmarker gardens allow two visits.` as an explicitly approved
   text source with a future review date. Add
   `Fictional internalmarker balcony contains staff details.` without approval.
2. Under Saved checks, select Customer. Add an answer check for
   `publicmarker gardens` with expected passage `two visits`, and a not-found
   check for `internalmarker balcony`. Run: both pass with only the approved source
   cited. Save the question file and download results. Reload the file: Customer
   mode and questions are restored. Load a legacy file: Staff is restored.
3. Select Staff and rerun the same questions. The staff-only question now returns a
   passage, so its not-found expectation fails. The displayed report is labelled
   Staff checks. This is an intentional expectation mismatch, not a retrieval error.
4. Restore Customer and explicitly review the public source while leaving customer
   approval unchecked. Rerun the unchanged set: the expected answer fails because
   retrieval abstains. Change that case to not found and rerun: it passes. No staff
   material is substituted. Removing or passing the deadline likewise excludes it.
5. Switch agents. Questions clear and the audience returns to Staff. Other agents'
   and organizations' approved sources cannot satisfy the selected agent's checks.

[Machine-readable API evidence](customer-knowledge-evaluation-local-2026-11-26.json)
records a four-case variant: approved answer, staff exclusion, overdue exclusion and
foreign-source exclusion. Customer initially passes 4/4, Staff passes 3/4, withdrawal
causes the original customer set to pass 3/4, and updated no-answer expectations pass
4/4. Only the explicit review changes source approval. The source-store calendar is
controlled at 2030-01-03; machine time is unchanged. This increment has automated
API and dashboard component evidence; no new browser walkthrough is claimed.

## Checks

- 20 new API cases: lifecycle and read-only boundaries for all 13 agents, plus seven
  invalid audience values. Covers restart expiry, removal, expected-answer injection,
  viewer reads, no source/review writes during evaluation and legacy staff responses.
- 14 new dashboard cases: customer requests, result labels/clearing, file/results
  save/load, legacy reset, agent switching, forged/mixed results and invalid files.
- Focused run: 70 API tests and 43 dashboard tests passed.
- Full backend: 2,510 passed, 156 skipped, four existing expected failures and
  662 passing subtests. Database-backed integration suites need their CI services.
- Full dashboard: 1,055 tests passed across 102 files.
- Type checking, production compilation, Ruff and focused Python typing passed.
  Dashboard lint has zero errors and 27 existing warnings. The local Windows build
  retains the existing standalone symlink packaging warning; use verified container
  artifacts for a later authorized release.

Hosted verification remains blocked by hosting access recovery. This change stays
on the existing unmerged PR; no deployment or merge is included.
