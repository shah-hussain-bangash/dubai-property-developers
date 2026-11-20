"""Private configuration staging, secret separation and non-disclosure tests."""

import json
import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_configuration_draft.py"))
CHECKER = runpy.run_path(str(ROOT / "apps/api/app/browser_readiness.py"))


class Tests(unittest.TestCase):
    def test_missing_identity_fields_remain_blank(self):
        draft = M["make_draft"]({}, CHECKER)
        for key in (
            "BROWSER_AUTH_OWNER_ID",
            "BROWSER_AUTH_ORGANIZATION_ID",
            "BROWSER_AUTH_TRUSTED_ORIGIN",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
        ):
            self.assertEqual(draft["settings"][key], "")

    def test_unknown_environment_keys_are_not_copied(self):
        draft = M["make_draft"]({"UNRELATED_PRIVATE_KEY": "never-copy"}, CHECKER)
        self.assertNotIn("never-copy", json.dumps(draft))
        self.assertEqual(set(draft["settings"]), set(CHECKER["ENV_KEYS"]))

    def test_draft_intends_token_mode_and_closed_registration(self):
        draft = M["make_draft"](
            {
                "AUTH_MODE": "dev",
                "ENABLE_DEV_ROUTES": "true",
                "BROWSER_AUTH_REGISTRATION_ENABLED": "true",
            },
            CHECKER,
        )
        self.assertEqual(draft["settings"]["AUTH_MODE"], "token")
        self.assertEqual(draft["settings"]["ENABLE_DEV_ROUTES"], "false")
        self.assertEqual(draft["settings"]["BROWSER_AUTH_REGISTRATION_ENABLED"], "false")
        self.assertFalse(draft["live_activation_ready"])

    def test_secrets_are_new_distinct_and_not_copied_from_source(self):
        draft = M["make_draft"]({key: "source-secret" for key in M["SECRET_KEYS"]}, CHECKER)
        values = [draft["settings"][key] for key in M["SECRET_KEYS"]]
        self.assertNotEqual(*values)
        self.assertTrue(all(len(value) == 64 and value != "source-secret" for value in values))

    def test_bad_or_repeating_secret_generator_is_rejected(self):
        for value in ("bad\nsecret", "a" * 64):
            with self.assertRaises(ValueError):
                M["make_draft"]({}, CHECKER, token_factory=lambda count, token=value: token)

    def test_safe_summary_contains_no_values_or_hashes(self):
        draft = M["make_draft"]({"GOOGLE_OAUTH_CLIENT_SECRET": "private-google-value"}, CHECKER)
        summary = json.dumps(M["safe_summary"](draft, CHECKER))
        for value in (
            "private-google-value",
            *(draft["settings"][key] for key in M["SECRET_KEYS"]),
        ):
            self.assertNotIn(value, summary)
        self.assertNotIn("sha256", summary)

    def test_private_json_roundtrip_does_not_expand_or_execute_text(self):
        value = 'literal $VALUE $(no-execution) "quotes"\nline'
        draft = M["make_draft"]({"GOOGLE_OAUTH_CLIENT_SECRET": value}, CHECKER)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "draft.json"
            M["write_draft"](path, draft, CHECKER)
            self.assertEqual(
                json.loads(path.read_bytes())["settings"]["GOOGLE_OAUTH_CLIENT_SECRET"], value
            )

    def test_existing_draft_is_preserved(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "draft.json"
            path.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                M["write_draft"](path, M["make_draft"]({}, CHECKER), CHECKER)
            self.assertEqual(path.read_bytes(), b"preserve")

    def test_selected_source_values_are_not_mutated(self):
        source = {
            "AUTH_MODE": "dev",
            "DATABASE_URL": "postgresql+asyncpg://user:private@localhost/app",
        }
        before = dict(source)
        M["make_draft"](source, CHECKER)
        self.assertEqual(source, before)

    def test_format_success_does_not_verify_owner_or_google(self):
        draft = M["make_draft"](
            {
                "BROWSER_AUTH_TRUSTED_ORIGIN": "https://accounts.example.invalid",
                "BROWSER_AUTH_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000001",
                "BROWSER_AUTH_OWNER_ID": "00000000-0000-0000-0000-000000000002",
                "GOOGLE_OAUTH_CLIENT_ID": "offline-test-client",
                "GOOGLE_OAUTH_CLIENT_SECRET": "offline-test-credential",
                "DATABASE_URL": "postgresql+asyncpg://user:password@localhost/app",
                "REDIS_URL": "redis://localhost:6379/0",
            },
            CHECKER,
        )
        summary = M["safe_summary"](draft, CHECKER)
        self.assertTrue(summary["environment_format"]["configuration_format_ready"])
        self.assertFalse(summary["owner_identity_reviewed"])
        self.assertFalse(summary["google_credentials_verified"])
        self.assertFalse(summary["live_activation_ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
