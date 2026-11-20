# Integration setup guide

Every integration has a **Protocol** (the contract), a **Mock** (the default), a **config schema** and,
where a public API is documented, an **HTTP adapter** built on `integrations/base.HttpIntegrationClient`.
That client provides auth injection, timeouts, retries on transport errors, 429 and 5xx (but not 4xx),
idempotency headers and redacted error details. Live mode is used only when `INTEGRATIONS_MODE=live`
**and** the integration's credentials are set; otherwise the mock is used.

| Integration | Status | To enable |
|---|---|---|
| **EspoCRM** | HTTP adapter (`/api/v1/Lead`, `/api/v1/Note`, `X-Api-Key`). Untested live | Create an API user in EspoCRM with Lead/Note access. Set `ESPOCRM_BASE_URL` and `ESPOCRM_API_KEY`. Verify the `source` option values in `agents/crm/mapping.py` |
| **Meta WhatsApp Business** | Cloud API adapter (`/{version}/{phone_number_id}/messages`). Untested live | Verified WhatsApp Business account, phone number ID, a permanent system-user token and app secret. Register and approve the templates you use (for example `follow_up_generic`). Webhook verification uses `META_APP_SECRET` |
| **Google (Calendar)** | Mock only | Implement a live adapter with a service account or OAuth. Set `GOOGLE_CREDENTIALS_FILE` |
| **Bayut** | Interface only | Requires an authorized partner/API agreement. **No scraping** |
| **Property Finder** | Interface only | Requires authorized partner/API access. **No scraping** |
| **Telephony** | Mock only. Provider not selected | Choose a provider, confirm UAE telecom requirements, implement `TelephonyClient` |
| **n8n** | HTTP adapter (POST `{base}/webhook/{path}`) | Set `N8N_WEBHOOK_BASE_URL`. Add header auth on the n8n webhook node and in `HttpN8nClient` |
| **Slack** | Incoming-webhook adapter | Set `SLACK_WEBHOOK_URL`. Internal staff alerts only; send IDs, not customer PII |

## Enabling a live integration safely

1. Test against a sandbox or test account first.
2. Keep `APPROVAL_REQUIRED_FOR_OUTBOUND_MESSAGES=true` while validating.
3. Add an integration test that runs only with credentials present and is skipped otherwise.
4. Check `GET /api/v1/integrations`: the integration should report `mode: live`, `configured: true`.
