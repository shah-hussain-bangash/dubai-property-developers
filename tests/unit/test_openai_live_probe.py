# ruff: noqa: E402 -- Standalone audit/path bootstrap must precede application imports.
"""Probe tests simulate every provider response and local credential prompt."""

import importlib.util
import io
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = (
    Path(sys.argv[1]).resolve()
    if __name__ == "__main__" and len(sys.argv) > 1
    else Path(__file__).resolve().parents[2]
)
if __name__ == "__main__" and len(sys.argv) > 1:
    del sys.argv[1]
sys.path.insert(0, str(ROOT))
guard = runpy.run_path(str(ROOT / "tests/unit/test_openai_responses_provider.py"))
import httpx
from pydantic import (
    SecretStr,
)

spec = importlib.util.spec_from_file_location(
    "tested_openai_probe", ROOT / "scripts/maintenance/openai_live_probe.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def completed(text="CONNECTION_OK"):
    body = guard["success"]()
    body["output"][0]["content"][0]["text"] = text
    return body


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_single_fixed_request_and_no_stored_payload(self):
        calls = []

        def handle(req):
            calls.append(json.loads(req.content))
            return httpx.Response(200, json=completed())

        result = await module.probe(
            "unit-model", SecretStr("unit-sensitive-key"), transport=httpx.MockTransport(handle)
        )
        self.assertEqual(result["outcome"], "live_text_probe_passed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["max_output_tokens"], 256)
        self.assertEqual(
            calls[0]["input"],
            [
                {
                    "role": "user",
                    "content": "This is a fictional software connection check. Return only CONNECTION_OK.",
                }
            ],
        )
        self.assertEqual(
            (calls[0]["store"], calls[0]["stream"], calls[0]["tools"]), (False, False, [])
        )
        self.assertNotIn("unit-sensitive-key", json.dumps(result))
        self.assertNotIn("unit-model", json.dumps(result))
        self.assertNotIn("CONNECTION_OK", json.dumps(result))

    async def test_invalid_models_rejected_before_http(self):
        calls = []
        for model in [
            "",
            "mock-deterministic",
            "sk-accidentally-pasted-key",
            "bad\nmodel",
            "/wrong",
        ]:
            result = await module.probe(
                model,
                SecretStr("unit-key"),
                transport=httpx.MockTransport(lambda req: calls.append(req)),
            )
            self.assertFalse(result["request_attempted"])
        self.assertEqual(calls, [])

    async def test_invalid_key_rejected_without_request(self):
        calls = []
        result = await module.probe(
            "unit-model",
            SecretStr(""),
            transport=httpx.MockTransport(lambda req: calls.append(req)),
        )
        self.assertFalse(result["request_attempted"])
        self.assertEqual(result["outcome"], "configuration_rejected")
        self.assertEqual(calls, [])

    async def test_unexpected_acknowledgement_is_not_reported_as_pass(self):
        result = await module.probe(
            "unit-model",
            SecretStr("unit-key"),
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json=completed("private unexpected response"))
            ),
        )
        self.assertTrue(result["request_completed"])
        self.assertFalse(result["acknowledgement_matched"])
        self.assertEqual(result["outcome"], "live_text_probe_unexpected_acknowledgement")
        self.assertNotIn("private unexpected response", json.dumps(result))

    async def test_auth_error_sanitized(self):
        result = await module.probe(
            "unit-model",
            SecretStr("unit-sensitive-key"),
            transport=httpx.MockTransport(
                lambda req: httpx.Response(401, text="private provider body unit-sensitive-key")
            ),
        )
        self.assertEqual(result["error_code"], "integration_not_configured")
        self.assertFalse(result["request_completed"])
        self.assertNotIn("private provider body", json.dumps(result))
        self.assertNotIn("unit-sensitive-key", json.dumps(result))

    async def test_rate_limit_never_retries(self):
        calls = []

        def handle(req):
            calls.append(req)
            return httpx.Response(429)

        result = await module.probe(
            "unit-model", SecretStr("unit-key"), transport=httpx.MockTransport(handle)
        )
        self.assertEqual((result["error_code"], len(calls)), ("rate_limited", 1))

    async def test_timeout_not_reported_as_completed(self):
        def handle(req):
            raise httpx.ReadTimeout("private timeout detail", request=req)

        result = await module.probe(
            "unit-model", SecretStr("unit-key"), transport=httpx.MockTransport(handle)
        )
        self.assertTrue(result["request_attempted"])
        self.assertFalse(result["request_completed"])
        self.assertNotIn("private timeout detail", json.dumps(result))

    async def test_incomplete_response_not_accepted(self):
        body = completed()
        body["status"] = "incomplete"
        result = await module.probe(
            "unit-model",
            SecretStr("unit-key"),
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)),
        )
        self.assertEqual(result["outcome"], "live_text_probe_failed")
        self.assertFalse(result["request_completed"])

    def cli(self, root, action, *, tty=True):
        output = io.StringIO()
        with (
            patch.object(module, "_preflight", return_value={}),
            patch.object(sys.stdin, "isatty", return_value=tty),
            patch.object(sys.stderr, "isatty", return_value=tty),
            patch("builtins.input", return_value="unit-model"),
            patch.object(module.getpass, "getpass", return_value="unit-sensitive-key"),
            patch.object(module, "probe", action),
            redirect_stdout(output),
        ):
            code = module.main(root)
        return code, output.getvalue()

    def temp_root(self, directory):
        root = Path(directory)
        (root / module.REPORT).parent.mkdir(parents=True)
        return root

    def test_noninteractive_terminal_never_reads_key_or_calls_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_root(directory)
            action = AsyncMock()
            code, _ = self.cli(root, action, tty=False)
            self.assertEqual(code, 1)
            action.assert_not_called()
            self.assertFalse((root / module.REPORT).exists())

    def test_cli_finalizes_own_reservation_without_sensitive_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_root(directory)

            async def action(model, key):
                self.assertEqual(
                    json.loads((root / module.REPORT).read_bytes())["outcome"],
                    "reserved_provider_outcome_not_confirmed",
                )
                return {
                    "outcome": "live_text_probe_passed",
                    "request_attempted": True,
                    "request_completed": True,
                    "acknowledgement_matched": True,
                    "input_tokens": 12,
                    "output_tokens": 3,
                    "error_code": None,
                }

            code, output = self.cli(root, action)
            self.assertEqual(code, 0)
            serialized = (root / module.REPORT).read_text(encoding="utf-8")
            self.assertNotIn("unit-sensitive-key", serialized + output)
            self.assertNotIn("unit-model", serialized + output)
            self.assertEqual(json.loads(serialized)["maximum_provider_requests"], 1)
            self.assertFalse(json.loads(serialized)["running_app_activated"])

    def test_existing_success_failure_or_reservation_blocks_new_attempts(self):
        for outcome in [
            "live_text_probe_passed",
            "live_text_probe_failed",
            "reserved_provider_outcome_not_confirmed",
        ]:
            with tempfile.TemporaryDirectory() as directory:
                root = self.temp_root(directory)
                report = root / module.REPORT
                original = json.dumps({"step": 613, "outcome": outcome}).encode()
                report.write_bytes(original)
                action = AsyncMock()
                code, _ = self.cli(root, action)
                self.assertEqual(code, 0)
                action.assert_not_called()
                self.assertEqual(report.read_bytes(), original)

    def test_interrupted_attempt_preserves_reservation_and_blocks_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_root(directory)
            code, _ = self.cli(root, AsyncMock(side_effect=KeyboardInterrupt))
            self.assertEqual(code, 1)
            self.assertEqual(
                json.loads((root / module.REPORT).read_bytes())["outcome"],
                "reserved_provider_outcome_not_confirmed",
            )
            action = AsyncMock()
            self.cli(root, action)
            action.assert_not_called()


if __name__ == "__main__":
    execution = unittest.main(verbosity=2, exit=False)
    assert guard["attempts"] == {"connections": 0, "held_execution": 0}
    sys.exit(0 if execution.result.wasSuccessful() else 1)
