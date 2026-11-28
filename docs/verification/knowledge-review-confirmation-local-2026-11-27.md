# Fresh customer approval after review confirmation changes

Verified locally on 27 November 2026 against parent
`c26ff936f94fdd82d9cce4243814645892b8c47c` plus this fix in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
The commit containing this record identifies the implementation. Verification uses
fictional dashboard component responses, not a new hosted or browser acceptance
journey.

## Observed blocker and fix

The saved-source review form already cleared review confirmation and customer
approval when its next review date changed. However, unchecking I have reviewed this
saved source left a previously selected customer approval checked. Rechecking review
could therefore carry that draft approval forward without a fresh customer-use
choice. Customer approval was also selectable before review was confirmed.

The form now clears its draft customer approval whenever review confirmation
changes. The customer-use checkbox remains disabled until a date is present and
review has been confirmed. Withdrawing review clears/disables customer approval and
blocks submission. Reconfirming review makes customer approval available but leaves
it unchecked. Staff can explicitly select it again before saving. Existing date-change
resets and unchecked approval on opening a review remain.

This is a draft-form safeguard. Toggling either checkbox does not immediately change
stored source approval, deadlines or review history. A stored source that is already
approved stays approved until a successful explicit review update changes it. Saving
a reconfirmed review without freshly selecting customer approval sends the existing
`reviewed: true, customer_safe: false` payload; selecting approval again sends true.
The page explains when draft approval is cleared.

No API schema, permission, ownership, saved text, review-history retention or source
retrieval policy changes. Existing API validation still requires explicit review and
approval booleans; the form cannot prove a human has actually checked the material.
No automatic approval, customer delivery or server-side revocation is added.

## Reproduce

1. In a disposable local mock-provider Knowledge workspace, open a fictional source's
   saved text and review form. Even if the source was previously approved, the new
   draft's customer approval is unchecked and disabled until review is confirmed.
2. Set a next review date, confirm I have reviewed this saved source, then select
   Approve this reviewed source for customer answers.
3. Uncheck review confirmation. Customer approval clears and disables, Save source
   review disables, and no PATCH occurs. The stored source remains unchanged.
4. Confirm review again. Approval becomes available but remains unchecked. Save
   without selecting it: the PATCH has `reviewed: true, customer_safe: false`, and
   the confirmed review leaves the source staff-only.
5. Repeat the withdrawal/reconfirmation, then explicitly select customer approval
   again before saving. The PATCH now has `customer_safe: true`. This preserves
   normal explicitly approved reviews.
6. Change the date after approval: the existing date reset still clears both review
   and approval confirmations, requiring the same explicit choices again.

## Validation

Three new component regressions failed before the fix while the preceding nine
review-form cases passed. All 12 review-form cases now pass. Tests inspect checkbox
availability/reset, no mutation on withdrawal, and the actual PATCH payload for
staff-only versus freshly approved saves. The combined review form, import approval
and review-date run passes 27 tests.

- Full dashboard: 1,152 tests passed across 109 files. Type checking and production
  compilation passed. Lint reports zero errors and 27 existing warnings.
- The Windows build retains its existing standalone symlink packaging warning;
  the local standalone folder is not a verified deployment artifact.
- Backend code is unchanged; existing backend suites run in GitHub CI.
- No live writes, customer messages, merge or deployment are included. Hosted
  verification remains pending hosting access recovery.
