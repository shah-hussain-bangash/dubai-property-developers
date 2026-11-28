# Multilingual question-file save/load size consistency

Verified locally on 27 November 2026 against parent
`b93ea73957a0504e617f6618b9441d759e1027df` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Verification uses
fictional dashboard fixtures; no new hosted or browser journey is claimed.

## Observed blocker

The editor allowed 20 cases, each with a 1,000-character question and expected
passage, and saved valid sets without a byte-size check. Loading then rejected files
larger than 100,000 bytes. A complete CJK-text set is valid under the editor's field
limits but its UTF-8 JSON download exceeds that threshold. The page could therefore
reject its own saved question file after the user switched away and tried to reload.
Both staff and customer audiences were affected.

## Change and boundaries

Saving and loading now share a 256,000-byte (256 KB) question-file budget. This
covers the current maximum 20-case schema, including UTF-8 multilingual text,
64-character case IDs, pretty-print overhead and six-byte JSON control-character
escapes. The serializer validates/normalizes the set through the existing parser,
measures actual UTF-8 Blob bytes and refuses an over-budget download. Loading checks
the same byte budget before reading/parsing the file. The editor and error message
state the limit.

The existing 20-case cap, per-field lengths, unique case IDs, agent/audience binding,
strict question-file schema and report validation remain. The existing oversized
fixture now tests just above the new bound; oversized input remains rejected before
its text reader runs. Older small question files continue to load. Expected passages
remain evaluation data and never become knowledge sources.

This limit applies only to local evaluation question JSON files. PDF/text/Markdown
source-upload limits, source-store limits, API body limits and result-report format
are unchanged. Reports still cannot be loaded as question sets. No server-side
question storage, model training, retrieval/translation changes or customer delivery
is added.

## Reproduce

1. In a disposable local mock-provider Knowledge dashboard, select Document Agent.
   In Saved checks, choose Staff. Create 20 answer cases, each with a question of
   `庭` repeated 1,000 times and an expected passage of `园` repeated 1,000 times.
   These are encoding fixtures, not a claim about answer quality or translation.
2. Save the question set. Independently inspect its actual Blob/file size: it is
   larger than 100,000 bytes but fits within 256,000. Parse the JSON and confirm
   all 20 cases are present.
3. Switch to Marketing Agent and back to Document Agent, clearing the editor. Load
   that exact generated file. All questions, expected passages and case IDs return.
   Save again: the parsed question object is identical to the first download.
4. Repeat using Customer mode. The downloaded and reloaded set retains customer
   audience; it does not silently become a staff set. No evaluation or source POST
   is issued merely by saving/loading these local files.
5. Select an input just above 256,000 bytes. It is rejected before its text is read,
   and the existing editor draft remains. Separately serialize a maximum-count,
   maximum-field-length schema fixture using six-byte JSON escapes: its actual
   encoded size still fits, and parsing reproduces the exact original set.

## Validation

Two new staff/customer component cases reproduced the own-download rejection
before the fix and now pass. They construct all 20 cases through the editor, capture
actual download Blobs, load a real-size File after an agent switch, and compare the
saved/reloaded JSON objects. Two further cases cover reject-before-read/draft
retention and maximum escaped-byte serialization. The combined file-size and
existing evaluation run passes 40 tests. The old oversized-input regression uses
the shared bound plus one byte; it is not removed or weakened into accepting
unbounded files. The two full-editor round trips have a bounded 15-second test
allowance for slower CI workers.

- Full dashboard: 1,156 tests passed across 110 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
