# Import review-date preflight — local verification

Date: 28 November 2026 (Dubai).
Parent revision: `44badf7bbbe5cfdac71bc3c592c171c50d636d13`.
Scope: PR #87, local API verification with fictional sources. No staging, production, CRM or email writes; no merge or deployment.

## Observed problem

An authorized website import with a correctly formatted but expired review date fetched the website before `AssignedSources.add` rejected the date. Raw PDF, text and Markdown uploads likewise ran extraction first. A failing fetch or parser could therefore mask an already-invalid deadline, and the work was unnecessary.

The pre-fix reproduction returned 422 but failed the assertion that the website importer was not called. One selected case failed, with 55 deselected. The website and extraction functions were stubbed: no real external website was contacted.

## Change

The existing store date rule is shared as `validate_import_review_date`. JSON imports validate the deadline before website fetching; raw file imports validate it after MIME/date parsing and before extraction. The store still rechecks the same rule before writing, including when an import crosses midnight or bypasses the API. The existing 422 message remains unchanged.

This does not change date syntax, customer approval, source identity, tenant/agent scoping, history or retrieval. Today is inclusive; future and omitted deadlines retain their existing behavior. Stored expired sources are not removed or renewed. Request bodies are still bounded/read before preflight; this does not claim to avoid upload transfer, authentication or all processing. Other invalid metadata and capacity errors are outside this focused change.

## Reproduction

From the repository root, with backend dependencies installed:

```powershell
python -m pytest tests/security/test_source_deadline_preflight.py -q -p no:cacheprovider
python -m pytest tests/security/test_source_deadline_preflight.py tests/security/test_source_import_strict_dates.py tests/security/test_source_import_strict_approval.py tests/security/test_uploaded_source_review_dates.py -q -p no:cacheprovider
```

The source-store clock alone is fixed at 2030-01-02; the machine clock is unchanged. The new suite submits 2030-01-01 through website/PDF/text/Markdown routes for all 13 registered agents. Each rejection must return 422, invoke neither fetching nor extraction, and preserve existing own/foreign tenant source snapshots. Four boundary cases then verify that omitted, same-day and future deadlines import normally and invoke the relevant importer once. Extraction is stubbed in these new orchestration tests; actual format extraction remains covered by the existing source-format suite.

## Results

- New regression cases: 56 passed as part of the focused run.
- Focused import/date/approval compatibility: 139 passed.
- Ruff checks, formatting and focused mypy: passed.
- Full backend suite: 2,617 passed, 156 skipped, four existing expected failures, 662 passing subtests and three warnings in 126.13 seconds. Skips include database-service integration cases, which run against disposable services in CI, and a Unix-only file-mode check. The existing expected failures concern recovery fencing; this change introduces no new skips or expected failures.

Frontend files are unchanged. Local API evidence does not establish hosted availability; hosted verification still depends on recovery of AWS access.
