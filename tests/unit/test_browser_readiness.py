"""Offline readiness checks with synthetic environment and migration fixtures."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "apps/api/app/browser_readiness.py"))
environment = module["inspect_environment"]
migrations = module["inspect_migrations"]
schema = module["assess_schema_columns"]


def values():
    return {
        "BROWSER_AUTH_TRUSTED_ORIGIN": "https://app.example.com",
        "BROWSER_AUTH_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000001",
        "BROWSER_AUTH_OWNER_ID": "00000000-0000-0000-0000-000000000002",
        "GOOGLE_OAUTH_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "fixture-google-credential-value",
        "BROWSER_AUTH_CSRF_SECRET": "a" * 48,
        "BROWSER_AUTH_SESSION_SECRET": "b" * 48,
        "DATABASE_URL": "postgresql+asyncpg://user:private-password@localhost/project",
        "REDIS_URL": "redis://:private-redis-password@localhost:6379/0",
        "AUTH_MODE": "token",
        "ENABLE_DEV_ROUTES": "false",
    }


def migration_fixture(root, revision, parent, name=None, staged=False):
    relative = (
        module["STAGED"][revision]
        if staged
        else "database/migrations/versions/" + (name or revision) + ".py"
    )
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"revision = {revision!r}\ndown_revision = {parent!r}\n", encoding="utf-8")
    return path


class Tests(unittest.TestCase):
    def test_environment_format_success_never_grants_activation(self):
        result = environment(values())
        self.assertTrue(result["configuration_format_ready"])
        self.assertFalse(result["live_activation_ready"])
        self.assertFalse(result["credential_authenticity_verified"])

    def test_missing_environment_is_explicit(self):
        result = environment({})
        self.assertFalse(result["configuration_format_ready"])
        self.assertEqual(result["checks"]["GOOGLE_OAUTH_CLIENT_SECRET"], "missing")
        self.assertEqual(result["checks"]["BROWSER_AUTH_REGISTRATION_ENABLED"], "format_ok")

    def test_no_environment_values_or_credentials_are_returned(self):
        supplied = values()
        output = json.dumps(environment(supplied))
        for key in (
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "BROWSER_AUTH_CSRF_SECRET",
            "BROWSER_AUTH_SESSION_SECRET",
            "DATABASE_URL",
            "REDIS_URL",
        ):
            self.assertNotIn(supplied[key], output)
        self.assertNotIn("private-password", output)
        self.assertNotIn("private-redis-password", output)

    def test_placeholder_and_shared_secrets_fail(self):
        for key, value in (
            ("GOOGLE_OAUTH_CLIENT_SECRET", "change-me"),
            ("BROWSER_AUTH_CSRF_SECRET", "synthetic-" + "a" * 48),
            ("BROWSER_AUTH_SESSION_SECRET", "a" * 48),
        ):
            with self.subTest(key=key):
                supplied = values()
                supplied[key] = value
                self.assertFalse(environment(supplied)["configuration_format_ready"])

    def test_uuid_nil_and_external_identity_are_rejected(self):
        for value in ("00000000-0000-0000-0000-000000000000", "google-subject"):
            supplied = values()
            supplied["BROWSER_AUTH_OWNER_ID"] = value
            self.assertEqual(
                environment(supplied)["checks"]["BROWSER_AUTH_OWNER_ID"], "invalid_or_unsafe"
            )

    def test_untrusted_origins_and_bad_ports_are_rejected(self):
        for value in (
            "http://localhost:8000",
            "https://user@app.example.com",
            "https://app.example.com/path",
            "https://app.example.com:bad",
            "https://app.example.com/#fragment",
        ):
            supplied = values()
            supplied["BROWSER_AUTH_TRUSTED_ORIGIN"] = value
            self.assertFalse(environment(supplied)["configuration_format_ready"])

    def test_development_mode_and_enabled_registration_are_blockers(self):
        for key, value in (
            ("AUTH_MODE", "dev"),
            ("ENABLE_DEV_ROUTES", "true"),
            ("BROWSER_AUTH_REGISTRATION_ENABLED", "true"),
        ):
            supplied = values()
            supplied[key] = value
            self.assertFalse(environment(supplied)["configuration_format_ready"])

    def test_invalid_connection_urls_are_sanitized(self):
        for key, value in (
            ("DATABASE_URL", "sqlite:///local.db"),
            ("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost"),
            ("REDIS_URL", "https://private:secret@localhost"),
            ("REDIS_URL", "redis://localhost:bad/0"),
        ):
            supplied = values()
            supplied[key] = value
            output = environment(supplied)
            self.assertEqual(output["checks"][key], "invalid_or_unsafe")
            self.assertNotIn(value, json.dumps(output))

    def test_active_project_reports_staged_auth_migrations_as_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            migration_fixture(root, "0008_tool_request_fingerprint", None)
            migration_fixture(
                root, "0009_user_account_approval", "0008_tool_request_fingerprint", staged=True
            )
            migration_fixture(
                root, "0010_account_auth_storage", "0009_user_account_approval", staged=True
            )
            result = migrations(root)
        self.assertFalse(result["required_migrations_registered"])
        self.assertEqual(
            result["staged_candidates"]["0010_account_auth_storage"], "metadata_matches"
        )

    def test_valid_migration_chain_can_be_recognized_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            migration_fixture(root, "0008_tool_request_fingerprint", None)
            migration_fixture(root, "0009_user_account_approval", "0008_tool_request_fingerprint")
            migration_fixture(root, "0010_account_auth_storage", "0009_user_account_approval")
            result = migrations(root)
        self.assertTrue(result["required_migrations_registered"])
        self.assertFalse(result["database_schema_verified"])
        self.assertFalse(result["migrations_applied"])

    def test_missing_directory_is_not_a_valid_graph(self):
        with tempfile.TemporaryDirectory() as folder:
            result = migrations(folder)
        self.assertFalse(result["migration_graph_valid"])

    def test_cycles_missing_parents_and_duplicate_revisions_fail_closed(self):
        for case in ("cycle", "missing_parent", "duplicate", "multiple_heads"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                if case == "cycle":
                    migration_fixture(root, "first", "second")
                    migration_fixture(root, "second", "first")
                elif case == "missing_parent":
                    migration_fixture(root, "first", "absent")
                elif case == "duplicate":
                    migration_fixture(root, "first", None)
                    migration_fixture(root, "first", None, name="duplicate")
                else:
                    migration_fixture(root, "first", None)
                    migration_fixture(root, "second", None)
                self.assertFalse(migrations(root)["migration_graph_valid"])

    def test_migration_source_is_parsed_and_never_executed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = migration_fixture(root, "first", None)
            path.write_text(path.read_text() + "\nraise RuntimeError('must never execute')\n")
            result = migrations(root)
        self.assertTrue(result["migration_graph_valid"])
        self.assertFalse(result["migration_source_executed"])

    def test_computed_or_invalid_revision_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = migration_fixture(root, "first", None)
            path.write_text("revision = make_revision()\ndown_revision = None\n")
            result = migrations(root)
        self.assertFalse(result["migration_graph_valid"])
        self.assertEqual(result["parse_failures"], 1)

    def test_wrong_staged_parent_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            migration_fixture(root, "0009_user_account_approval", "wrong", staged=True)
            result = migrations(root)
        self.assertEqual(
            result["staged_candidates"]["0009_user_account_approval"], "metadata_mismatch"
        )

    def test_schema_columns_do_not_prove_constraints_or_activation(self):
        result = schema(module["SCHEMA_COLUMNS"])
        self.assertTrue(result["required_columns_present"])
        self.assertFalse(result["constraints_verified"])
        self.assertFalse(result["live_activation_ready"])

    def test_missing_schema_tables_and_columns_are_reported(self):
        result = schema({"users": ["id"]})
        self.assertFalse(result["required_columns_present"])
        self.assertIn("token_digest", result["missing_columns"]["account_sessions"])
        self.assertIn("approval_status", result["missing_columns"]["users"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
