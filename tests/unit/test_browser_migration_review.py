"""Offline SQL and source checks; no application environment or database."""

import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "scripts/maintenance/browser_migration_review.py"))
readiness = runpy.run_path(str(ROOT / "apps/api/app/browser_readiness.py"))
VERSIONS = ROOT / "database/migrations/versions"
APPROVAL = "0009_user_account_approval"
STORAGE = "0010_account_auth_storage"


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approval = module["emit_upgrade_sql"](VERSIONS / (APPROVAL + ".py"), APPROVAL)
        cls.storage = module["emit_upgrade_sql"](VERSIONS / (STORAGE + ".py"), STORAGE)

    def test_active_migrations_are_exact_staged_copies(self):
        for revision, staged in readiness["STAGED"].items():
            self.assertEqual(
                (VERSIONS / (revision + ".py")).read_bytes(), (ROOT / staged).read_bytes()
            )

    def test_registered_graph_is_valid_and_has_authentication_storage_head(self):
        result = readiness["inspect_migrations"](ROOT)
        self.assertTrue(result["required_migrations_registered"])
        self.assertEqual(result["active_heads"], [STORAGE])
        self.assertFalse(result["database_schema_verified"])

    def test_all_offline_sql_checks_pass_without_claiming_database_acceptance(self):
        result = module["assess_upgrade_sql"](self.approval, self.storage)
        self.assertTrue(result["offline_sql_checks_passed"])
        self.assertFalse(result["database_behavior_verified"])
        self.assertFalse(result["migration_applied"])
        self.assertFalse(result["live_activation_ready"])

    def test_old_approval_rows_are_not_rewritten(self):
        self.assertIn("ADD COLUMN approval_status VARCHAR(16)", self.approval)
        self.assertNotIn("ADD COLUMN approval_status VARCHAR(16) DEFAULT", self.approval)
        self.assertNotIn("UPDATE users", self.approval)
        self.assertLess(
            self.approval.index("ADD COLUMN approval_status"),
            self.approval.index("SET DEFAULT 'pending'"),
        )

    def test_tenant_foreign_keys_and_identity_uniqueness_are_rendered(self):
        self.assertEqual(self.storage.count("REFERENCES users (organization_id, id)"), 2)
        self.assertIn("UNIQUE (organization_id, issuer, subject)", self.storage)

    def test_tokens_are_represented_by_unique_digests(self):
        self.assertIn("token_digest VARCHAR(64) NOT NULL", self.storage)
        self.assertIn("UNIQUE (token_digest)", self.storage)
        self.assertNotIn("access_token", self.storage)

    def test_sql_generation_is_repeatable_and_does_not_modify_inputs(self):
        path = VERSIONS / (STORAGE + ".py")
        before = path.read_bytes()
        self.assertEqual(module["emit_upgrade_sql"](path, STORAGE), self.storage)
        self.assertEqual(path.read_bytes(), before)

    def test_upgrade_data_rewrites_and_drops_fail_review(self):
        for extra in (
            "\nUPDATE users SET approval_status = 'approved';",
            "\nDROP TABLE users;",
            "\nINSERT INTO users VALUES (1);",
            "\nTRUNCATE users;",
        ):
            with self.subTest(extra=extra):
                result = module["assess_upgrade_sql"](self.approval + extra, self.storage)
                self.assertFalse(result["offline_sql_checks_passed"])

    def test_missing_constraints_fail_review(self):
        damaged = self.storage.replace("ck_account_session_expiry", "missing_expiry_constraint")
        self.assertFalse(
            module["assess_upgrade_sql"](self.approval, damaged)["offline_sql_checks_passed"]
        )

    def test_unreviewed_import_or_top_level_call_is_rejected_before_execution(self):
        source = (VERSIONS / (APPROVAL + ".py")).read_text()
        for suffix in (
            "\nimport os\n",
            "\nraise RuntimeError('should not execute')\n",
            "\nprint('should not execute')\n",
        ):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                module["validate_source"](source + suffix, APPROVAL)

    def test_unreviewed_operations_are_rejected(self):
        source = (VERSIONS / (APPROVAL + ".py")).read_text()
        for replacement in ("op.execute(", "sa.create_engine("):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                module["validate_source"](
                    source.replace("op.add_column(", replacement, 1), APPROVAL
                )

    def test_revision_or_parent_mismatch_is_rejected(self):
        source = (VERSIONS / (APPROVAL + ".py")).read_text()
        for changed in (
            source.replace(APPROVAL, "wrong_revision"),
            source.replace("0008_tool_request_fingerprint", "wrong_parent"),
        ):
            with self.assertRaises(ValueError):
                module["validate_source"](changed, APPROVAL)

    def test_unknown_revision_and_computed_metadata_are_rejected(self):
        source = (VERSIONS / (APPROVAL + ".py")).read_text()
        with self.assertRaises(ValueError):
            module["validate_source"](source, "unknown")
        with self.assertRaises(ValueError):
            module["validate_source"](
                source.replace('revision = "' + APPROVAL + '"', "revision = compute_revision()"),
                APPROVAL,
            )

    def test_invalid_source_never_reaches_runpy_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.py"
            path.write_text("raise RuntimeError('must not execute')\n")
            with self.assertRaises(ValueError):
                module["emit_upgrade_sql"](path, APPROVAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
