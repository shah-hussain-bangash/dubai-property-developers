"""Private draft editing contracts."""

import copy
import json
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_configuration_intake.py"))
D = runpy.run_path(str(ROOT / "scripts/maintenance/browser_configuration_draft.py"))
C = runpy.run_path(str(ROOT / "apps/api/app/browser_readiness.py"))


class Tests(unittest.TestCase):
    def setUp(self):
        self.doc = D["make_draft"]({}, C)

    def test_only_five_fields_editable(self):
        self.assertEqual(len(M["EDITABLE"]), 5)
        for key in set(C["ENV_KEYS"]) - set(M["EDITABLE"]):
            with self.assertRaises(ValueError):
                M["update_draft"](self.doc, {key: "x"}, C)

    def test_new_values_are_copied_and_input_unchanged(self):
        before = copy.deepcopy(self.doc)
        edits = {key: "private-sentinel" for key in M["EDITABLE"]}
        updated = M["update_draft"](self.doc, edits, C)
        self.assertEqual(self.doc, before)
        self.assertTrue(all(updated["settings"][key] == value for key, value in edits.items()))

    def test_blank_keeps_existing_values(self):
        self.doc["settings"]["GOOGLE_OAUTH_CLIENT_ID"] = "existing-id"
        updated = M["update_draft"](self.doc, {"GOOGLE_OAUTH_CLIENT_ID": ""}, C)
        self.assertEqual(updated, self.doc)

    def test_dedicated_secrets_preserved(self):
        updated = M["update_draft"](self.doc, {}, C)
        for key in D["SECRET_KEYS"]:
            self.assertEqual(updated["settings"][key], self.doc["settings"][key])

    def test_editable_approval_flags_never_grant_activation(self):
        for key in (
            "owner_identity_reviewed",
            "google_credentials_verified",
            "live_activation_ready",
        ):
            self.doc[key] = True
        self.doc["settings"].update(
            AUTH_MODE="dev", ENABLE_DEV_ROUTES="true", BROWSER_AUTH_REGISTRATION_ENABLED="true"
        )
        updated = M["update_draft"](self.doc, {}, C)
        self.assertFalse(updated["live_activation_ready"])
        self.assertFalse(updated["owner_identity_reviewed"])
        self.assertFalse(updated["google_credentials_verified"])
        self.assertEqual(updated["settings"]["AUTH_MODE"], "token")
        self.assertEqual(updated["settings"]["ENABLE_DEV_ROUTES"], "false")
        self.assertEqual(updated["settings"]["BROWSER_AUTH_REGISTRATION_ENABLED"], "false")

    def test_schema_and_version_rejected(self):
        for change in (
            {"unknown": 1},
            {"version": True},
            {"version": 2},
            {"purpose": "other"},
            {"live_activation_ready": "true"},
        ):
            with self.assertRaises(ValueError):
                M["update_draft"]({**self.doc, **change}, {}, C)

    def test_settings_schema_rejected(self):
        for settings in ({}, [], {**self.doc["settings"], "other": "x"}):
            with self.assertRaises(ValueError):
                M["update_draft"]({**self.doc, "settings": settings}, {}, C)

    def test_invalid_values_rejected_without_disclosure(self):
        for value in (None, 10, [], "secret\nvalue", "secret\x00value", "x" * 4097):
            with self.assertRaisesRegex(ValueError, "^Invalid configuration value$"):
                M["update_draft"](self.doc, {"GOOGLE_OAUTH_CLIENT_SECRET": value}, C)

    def test_bounded_json_and_duplicate_fields_rejected(self):
        for data in (b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b"\xff", b" " * 131073, b"not-json"):
            with self.assertRaises(ValueError):
                M["decode_private"](data)
        self.assertEqual(M["decode_private"](json.dumps(self.doc).encode()), self.doc)

    def test_summary_contains_no_private_values(self):
        updated = M["update_draft"](self.doc, {"GOOGLE_OAUTH_CLIENT_SECRET": "private-sentinel"}, C)
        summary = json.dumps(D["safe_summary"](updated, C))
        for value in ("private-sentinel", *[self.doc["settings"][key] for key in D["SECRET_KEYS"]]):
            self.assertNotIn(value, summary)
        self.assertFalse(D["safe_summary"](updated, C)["live_activation_ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
