# Selected-agent saved knowledge download

Verified locally on 26 November 2026 against parent
`5fe0faff72999e6b6dfc6485f036c822108b3298` plus this increment in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All source text
and accounts in the tests are fictional; providers are mocked and no live messages
or CRM writes occurred.

## Behavior and limits

Saved sources now offers **Download saved knowledge** for the selected agent. It
prepares `<agent>-saved-knowledge.json`, containing the saved extracted text,
original PDF page numbers (including blank pages), source IDs/titles/kinds, website
snapshot URLs, character counts, creation times, review dates and customer-approval
flags. A UTC export preparation timestamp and format `agent-source-text-v1` identify
the copy. The format is separate from evaluation question sets.

The authenticated `GET /api/v1/knowledge/agents/{agent}/export` requires existing
knowledge-read access, verifies the registered agent, and selects records by trusted
organization and agent in one SQL read. Responses are private/no-store. Viewer
access matches existing saved-text preview access. Empty agents produce a valid
empty manifest. Identical content owned by other agents or organizations cannot
enter this copy. Original uploads, credentials, review history, evaluation files,
conversation memory and other workspace records are excluded.

The file includes staff-only and overdue sources, as a staff saved-text copy.
Keeping an expired source in the file does not make it eligible to answer questions.
Approval and dates are recorded metadata; downloading never changes permissions,
source content, deadlines, review events or retrieval behavior. Keep the file
private, as explained beside the button and in the prepared-download notice.

This is not an original-file export, complete database backup or automatic restore
format. The application deliberately rejects this manifest as a source import or
question set. Existing private SQLite/portal/PostgreSQL backup and release cutover
requirements remain. No restore endpoint, cross-agent transfer or customer delivery
is added. Manual re-use of text requires the existing import/review process.

The dashboard validates format, selected agent, UTC timestamp, unique source IDs,
source/page structure, Unicode code-point counts, dates, approval flags and existing
100-source/two-million-character limits before preparing the JSON download. The
agent stays locked during the request; failed or wrong-owner responses create no
file, and a late response after cancellation/unmount is ignored. Source drafts stay
intact. Browser download settings determine where the prepared file is saved.

## Reproduce

1. Start a disposable local mock-provider API/dashboard with private source storage.
   Select Document Agent and save fictional PDF, Markdown, website snapshot and
   pasted-text sources. Include a two-page PDF with a blank first page and Unicode
   text on Page 2. Keep at least one source staff-only.
2. Use the source-store test calendar to let one dated source become overdue.
   Keep another agent's and organization's sources separate. Do not change machine
   time or production configuration.
3. Click Download saved knowledge. Confirm `documents-saved-knowledge.json` has
   `format: "agent-source-text-v1"`, `agent_id: "documents"`, a UTC timestamp and
   exactly the selected agent's four source records. Check the PDF's Page 1 empty
   text and Page 2 Unicode content, website URL and review/approval metadata.
4. Independently read the disposable store and review history: both match the
   pre-download records. Customer queries still exclude the overdue PDF. An empty
   agent downloads an empty manifest. Source removal affects a subsequent download,
   while a previously downloaded copy retains its snapshot.
5. Load the export as a saved-check question file: it is rejected. Sending it to the
   source-import or evaluation endpoints likewise fails without source writes.
6. Simulate a failed export request or wrong-agent response: no file is prepared.
   Retry normally, then switch agents and verify the next request/filename uses the
   new agent. Closing the page before a delayed response must not download a file.

[Structured local API evidence](agent-source-export-local-2026-11-26.json) contains
only the fictional four-format export and assertions about unchanged storage,
exclusions and rejected re-use. This increment has real local API and automated
dashboard component evidence; no new browser walkthrough is claimed.

## Validation

- Fourteen new API/storage cases cover all 13 agents/four formats, scoped viewer
  reads, foreign exclusions, PDF/Unicode fidelity, expiry, restart, unchanged source
  and review history, deletion refresh, invalid reuse, empty exports and auth.
- Seventeen new dashboard cases cover validated file contents/name, Unicode,
  retained drafts, no mutation requests, agent locking/routing, failed retry,
  wrong-owner rejection, cancelled late responses and malformed export metadata.
  The focused dashboard run passed 28 tests.
- Full backend: 2,527 passed, 156 skipped, four existing expected failures and
  662 passing subtests. Database integration services run separately in CI.
- Full dashboard: 1,087 passed across 104 files. Type checking, production
  compilation, Ruff, formatting and focused mypy passed. Dashboard lint has zero
  errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified release artifact.

The existing PR remains unmerged and undeployed. Hosted acceptance still requires
hosting access recovery and the normal release conditions.
