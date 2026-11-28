# Lead planning organization checks

Verified locally on 25 November 2026 against PR #87 revision
`b0dce3279f9c48ab33ab05e948bd66a310f7fa32` plus this change.

## Observed issue

Marketing accepted supplied leads labelled as belonging to another organization
and included them in segments, audience counts or consent-exclusion counts. It
could query campaign sources for a mixed batch. Contextual qualification scoring
also accepted a foreign lead model and returned a score/routing plan for it.
The initial 16-case regression run reported 13 failures and three passing controls.
This concerns supplied-model ownership, not fetching previously unknown private
CRM records.

## Correction

Marketing checks principal/context identity and every supplied lead organization
before consent filtering, segmentation or source lookup. A mixed batch fails
without partial segments or drafts, even when the foreign lead lacks consent.
The scoring tool's contextual entry point checks both identity and lead ownership;
the qualification agent reaches that entry point through the existing gateway.
Direct contextual/agent calls retain these checks as well.

Existing permissions, allowlists, consent filters, approved-source selection,
qualification weights and routing rules are unchanged. The standalone scoring
helper remains a pure supplied-data calculation with no runtime-record access.

## Verification

All **16 new cases passed** across fixture/source-only modes: foreign/mixed campaign
inputs with/without consent, no source lookup after denial, foreign qualification,
normal owned segmentation and source-backed copy, normal qualification, direct
identity checks and standalone calculation compatibility. The focused planning,
marketing, agent, scoring and analytics suite passed **73 tests**.

The full local Python 3.14 suite reported **1,892 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for six marketing/analytics source files passed.

```text
python -m pytest tests/security/test_lead_planning_ownership.py tests/agents/test_marketing_assigned_sources.py tests/agents/test_agents.py tests/unit/test_scoring_and_matching.py tests/security/test_analytics_organization_scope.py -q
python -m pytest -q
python -m mypy agents/marketing tools/analytics
```

## Limits

The checks compare supplied lead metadata with trusted execution identity; they
do not add authoritative lead-ID lookups or attest to the origin of caller-provided
facts. Marketing still prepares drafts only and has no campaign sending capability.
No CRM data fetch, live write, model training, customer message, merge or deployment
was added.
