"""Webhook credentials stay out of request logs, diagnostics, and structured data."""

import io
import json
import logging
import sys
import unittest

import httpx

from core.observability.logging import JsonFormatter, RedactingTextFormatter, RedactionFilter
from core.resilience.retry import RetryPolicy
from core.security.redaction import REDACTED, redact_text, redact_value
from integrations.base import HttpIntegrationClient, NoAuth

WEBHOOK_PATH = "/services/TDEMO/BDEMO/webhook-demo-value"
WEBHOOK_URL = "https://hooks.slack.com" + WEBHOOK_PATH


class WebhookRedactionTests(unittest.TestCase):
    def test_webhook_urls_are_redacted_across_supported_hosts(self):
        for host in ("hooks.slack.com", "hooks.slack-gov.com", "HOOKS.SLACK.COM"):
            for scheme in ("http", "https"):
                with self.subTest(host=host, scheme=scheme):
                    url = f"{scheme}://{host}{WEBHOOK_PATH}?fixture=value"
                    self.assertEqual(redact_text(f"request {url} failed"), f"request {REDACTED} failed")

    def test_redaction_is_independent_of_pii_masking(self):
        self.assertEqual(redact_text(WEBHOOK_URL, mask_pii=False), REDACTED)

    def test_quotes_delimit_webhook_urls_without_removing_surrounding_fields(self):
        text = json.dumps({"url": WEBHOOK_URL, "status": "failed"})
        self.assertEqual(json.loads(redact_text(text)), {"url": REDACTED, "status": "failed"})

    def test_nested_payload_is_redacted_without_mutating_input(self):
        payload = {"diagnostics": [{"endpoint": WEBHOOK_URL}]}
        self.assertEqual(redact_value(payload), {"diagnostics": [{"endpoint": REDACTED}]})
        self.assertEqual(payload["diagnostics"][0]["endpoint"], WEBHOOK_URL)

    def test_unrelated_urls_are_preserved(self):
        for url in (
            "https://api.slack.com/methods/chat.postMessage",
            "https://hooks.slack.com.example.test/services/demo",
            "https://example.test/services/demo",
        ):
            with self.subTest(url=url):
                self.assertEqual(redact_text(url), url)

    def test_formatted_request_logs_hide_webhook_credentials(self):
        for formatter in (
            JsonFormatter(),
            RedactingTextFormatter("%(message)s"),
        ):
            with self.subTest(formatter=type(formatter).__name__):
                stream = io.StringIO()
                handler = logging.StreamHandler(stream)
                handler.addFilter(RedactionFilter())
                handler.setFormatter(formatter)
                record = logging.LogRecord(
                    "httpx",
                    logging.INFO,
                    __file__,
                    1,
                    'HTTP Request: %s %s "HTTP/1.1 200 OK"',
                    ("POST", WEBHOOK_URL),
                    None,
                )
                record.endpoint = WEBHOOK_URL
                handler.handle(record)
                output = stream.getvalue()
                self.assertNotIn(WEBHOOK_PATH, output)
                self.assertIn(REDACTED, output)

    def test_exception_diagnostics_hide_webhook_credentials(self):
        try:
            raise RuntimeError(f"request failed: {WEBHOOK_URL}")
        except RuntimeError:
            exc_info = sys.exc_info()
        for formatter in (JsonFormatter(), RedactingTextFormatter("%(message)s")):
            with self.subTest(formatter=type(formatter).__name__):
                record = logging.LogRecord(
                    "fixture", logging.ERROR, __file__, 1, "failed", (), exc_info
                )
                self.assertNotIn(WEBHOOK_PATH, formatter.format(record))


class IntegrationRequestLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_client_does_not_log_credential_paths_or_queries(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"ok": True})

        client = HttpIntegrationClient(
            integration="slack",
            base_url="https://hooks.example.test",
            auth=NoAuth(),
            retry_policy=RetryPolicy(max_attempts=1),
            transport=httpx.MockTransport(handler),
        )
        try:
            with self.assertLogs("integrations.base", level="INFO") as captured:
                await client.request("POST", WEBHOOK_PATH + "?fixture=private")
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].url.path, WEBHOOK_PATH)
            record = captured.records[0]
            self.assertEqual(record.integration, "slack")
            self.assertEqual(record.method, "POST")
            self.assertNotIn("path", record.__dict__)
            self.assertNotIn(WEBHOOK_PATH, repr(record.__dict__))
            self.assertNotIn("fixture=private", repr(record.__dict__))
        finally:
            await client.aclose()
