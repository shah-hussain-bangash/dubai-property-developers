# Integration redirect rejection — local, 25 November 2026

Revision: PR #87 parent `f73bf8bf96138344f4692190b6533cef1a5be672` plus this change.

## Observed issue and change

The shared HTTP integration client returned 3xx bodies as successful data, or returned
None for empty redirects. A mocked Slack notification therefore completed without
a delivery acknowledgement when the webhook returned an empty 302 response.

The client now rejects all 3xx responses as non-retryable integration errors before
decoding the body. Redirect following is explicitly disabled. Error details retain
only the status, excluding the redirect target and response body.

## Reproduction and results

All requests use httpx.MockTransport and fictional provider URLs. No live service is contacted.

```powershell
python -m pytest tests/security/test_integration_redirect_rejection.py tests/unit/test_integration_response_modes.py tests/unit/test_integration_origin_boundary.py tests/unit/test_integration_request_snapshots.py tests/security/test_webhook_log_redaction.py tests/integration/test_integration_adapters.py -q -p no:cacheprovider
python -m mypy --cache-dir=nul integrations/base.py
python -m ruff check --no-cache integrations/base.py tests/security/test_integration_redirect_rejection.py
python -m ruff format --check --no-cache integrations/base.py tests/security/test_integration_redirect_rejection.py
```

Before the fix, all 16 new regressions failed. After the fix, the focused run passed
49 tests and 20 subtests. The focused type check passed with caching disabled.
Initial lint identified two nested context-manager style issues in the new tests;
the published tests combine those context managers.

The full local run and final local lint rerun were blocked by zero free space on
drive C, which subsequently prevented local commands from starting. GitHub CI must
verify the published revision before relying on this change. The prior revision's
1,991-test local result is not a full local result for this revision.

Coverage includes 300/301/302/303/304/307/308 responses in JSON and text modes, an
empty Slack redirect, and a transient 503 followed by a redirect. Redirects are not
followed or retried; existing successful acknowledgements, empty 204 responses and
transient-error recovery remain covered by the focused suite.

## Limits

This does not establish live provider compatibility or exactly-once delivery.
No merge, deployment or live CRM, email, calendar or WhatsApp write is performed.
