# Source review deadline preservation

Verified locally on 25 November 2026 against PR #87 revision
`c75bc82897b9f3dabd0d9f195da7b18e3cf5ebb2` plus this change.

## Observed issue

Adding identical source content updates its existing metadata. An omitted review
date was passed as `None`, and the update cleared the stored deadline. Re-importing
expired content could therefore make it answerable again without a replacement
review date, including when executing a previously queued source-backed email.
Raw file imports could erase an existing deadline the same way. The initial
12-case regression run reported 11 failures and one passing renewal control.

## Correction

The existing atomic metadata update now preserves the stored `review_by` value
when the input date is omitted or null. An explicit replacement date still uses
the existing today-or-later validation and can renew expired content. Source IDs,
creation times, organization/agent scoping, title/approval updates and capacity
limits retain their existing behavior. New undated sources remain supported.
No schema migration or historical data rewrite is required for this code change.

## Verification

All **12 new cases passed**: omitted/null dates; expired extracted text, Markdown,
PDF and website sources; explicit renewal and new undated sources; JSON text/web
re-imports; raw text/Markdown uploads; and rejection of an approved queued email
after expired content is re-imported without a new date. Its mock outbox remains
empty. The combined deadline/source-approval/API suite passed **74 tests**.

The full local Python 3.14 suite reported **1,876 passed, 155 skipped, four existing
expected failures and 662 passing subtests**, with three existing dependency or
configuration warnings. Integration skips require explicitly enabled services;
expected failures concern existing recovery/fencing gaps. Ruff, formatting and
mypy for the supplied-source store passed.

```text
python -m pytest tests/security/test_source_review_deadline_preservation.py tests/security/test_source_bound_approvals.py tests/unit/test_assigned_agent_knowledge.py tests/security/test_assigned_source_api_isolation.py -q
python -m pytest -q
python -m mypy knowledge/assigned_sources.py
```

## Limits

Preservation applies to the same content-derived source identity in its own
organization/agent scope. Changed content/URI or an explicit remove-and-add is
not a duplicate metadata update. Null no longer clears an existing deadline;
provide a valid replacement date to renew it. This does not make review dates
mandatory, add new dashboard date controls, or recover deadlines already lost
before the fix. No live CRM writes, customer messages, merge or deployment occurred.
