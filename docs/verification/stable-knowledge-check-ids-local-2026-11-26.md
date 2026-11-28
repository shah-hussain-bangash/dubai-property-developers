# Stable references in saved knowledge checks

Verified locally on 26 November 2026 against parent
`50fd367e0d6d38846dc7341710e962767247eb78` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. All examples are
fictional. This is dashboard component verification; no new hosted or browser
acceptance journey is claimed.

## Observed blocker and fix

Loading a valid per-agent question file renamed every supplied case ID to
`case-1`, `case-2`, etc. For example, `garden-policy-v2` became `case-1` on the next
save and evaluation request. That lost the file author's reference linking a
question to earlier evaluation evidence. Both staff and customer question files
were affected. API evaluation already accepts valid custom IDs and preserves them.

The editor now retains the validated original IDs when loading a set. Editing,
removing and adding questions do not rename surviving cases. Run requests, saved
question files and downloaded question/result pairs carry those same references.
New questions use the first unused `case-N` in the current set. Allocation compares
opaque IDs as strings rather than parsing imported numeric suffixes, so custom IDs,
number gaps and very large numeric-looking IDs do not cause collisions or invalid
new IDs. The existing 20-question limit is also enforced inside the state update.

No API, source retrieval, question-file schema, expected passage matching, audience
policy or result validation changes. Old numbered files still load. Files already
renumbered by an earlier version do not regain lost references automatically; load
the original file to retain its original IDs. Generated IDs identify cases within
the current file, not a permanent server-wide identity or dataset version.

## Reproduce

1. Use the existing local mock-provider Knowledge workspace and Document Agent.
   Save a fictional source containing
   `Fictional project contains eight gardens.`.
2. Prepare this staff question file:

   ```json
   {
     "agent_id": "documents",
     "cases": [{
       "id": "garden-policy-v2",
       "question": "project gardens",
       "expectation": "answer",
       "expected_excerpt": "eight gardens"
     }]
   }
   ```

3. Load it and Save question set. Confirm the saved case ID is still
   `garden-policy-v2`. Run saved checks and download results: the request, question
   file and result case ID match. For Customer mode, explicitly approve the source
   and use the same file with top-level `"audience": "customer"`.
4. Load two valid cases with IDs `case-2` and
   `case-999999999999999999999999999999`. Add and complete another question. Its
   ID is `case-1`; both imported references remain intact. Remove the first question
   and save again: the surviving long ID and `case-1` remain unchanged.
5. Duplicate or malformed IDs remain rejected by the existing file parser. Switching
   agents still clears the editor, and report validation still checks exact case
   IDs, order, audience, citations and calculated outcomes.

## Evidence and validation

Three new component regressions reproduced the blocker before the fix: all three
failed while the preceding 33 evaluation tests passed. After the fix, all 36
passed; the combined evaluation/customer-preview run passed 46 tests.

The regressions read the actual prepared download blobs, compare original and
saved question objects, inspect evaluation requests, verify matching report
references, and exercise arbitrary/large IDs plus add/remove operations. They do
not accept the implementation's generated output as the expected fixture.

- Full dashboard: 1,090 tests passed across 104 files. Type checking and production
  compilation passed. Lint has zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing backend suites run in GitHub CI.
- No live messages, source writes, merge or deployment are included. Hosted
  acceptance remains pending hosting access recovery.
