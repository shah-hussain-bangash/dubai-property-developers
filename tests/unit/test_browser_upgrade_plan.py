"""Review the observed migration range without a live database or application env."""

import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "scripts/maintenance/browser_upgrade_plan.py"))
review = runpy.run_path(str(ROOT / "scripts/maintenance/browser_migration_review.py"))


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = module["build_upgrade_plan"](ROOT, [module["BASE"]])

    def test_all_four_pending_revisions_are_in_order(self):
        self.assertEqual(self.plan["pending_revisions"], list(module["CHAIN"]))
        self.assertEqual(self.plan["base_revision"], "0006_job_recovery_operations")
        self.assertEqual(self.plan["target_revision"], "0010_account_auth_storage")

    def test_full_range_has_a_transaction_and_alembic_bookkeeping(self):
        sql = self.plan["sql"]
        self.assertTrue(sql.startswith("BEGIN;"))
        self.assertTrue(sql.rstrip().endswith("COMMIT;"))
        self.assertEqual(sql.count("UPDATE public.alembic_version"), 4)
        self.assertNotIn("CREATE TABLE public.alembic_version", sql)

    def test_ledger_jsonb_and_nullable_fingerprint_are_preserved(self):
        sql = " ".join(self.plan["sql"].lower().split())
        self.assertIn("result_json jsonb", sql)
        self.assertIn("add column request_fingerprint varchar(64)", sql)
        self.assertNotIn("add column request_fingerprint varchar(64) not null", sql)

    def test_prior_approval_and_authentication_safety_checks_are_preserved(self):
        sql = self.plan["sql"]
        self.assertNotIn("UPDATE users", sql)
        self.assertNotIn("ADD COLUMN approval_status VARCHAR(16) DEFAULT", sql)
        self.assertIn("SET DEFAULT 'pending'", sql)
        self.assertIn("fk_account_session_tenant_user", sql)
        self.assertIn("uq_account_session_token_digest", sql)

    def test_schema_plan_is_not_database_acceptance(self):
        self.assertTrue(self.plan["assessment"]["offline_plan_checks_passed"])
        self.assertFalse(self.plan["assessment"]["database_behavior_verified"])
        self.assertFalse(self.plan["database_migrations_applied"])
        self.assertEqual(self.plan["database_connections"], 0)

    def test_other_or_multiple_database_heads_are_rejected(self):
        for heads in ([], ["0008_tool_request_fingerprint"], [module["BASE"], "other"]):
            with self.subTest(heads=heads), self.assertRaises(ValueError):
                module["build_upgrade_plan"](ROOT, heads)

    def test_existing_source_files_are_unchanged(self):
        paths = [
            ROOT / f"database/migrations/versions/{revision}.py" for revision in module["CHAIN"]
        ]
        paths += [ROOT / "database/base.py", ROOT / "database/migrations/env.py"]
        before = {path: path.read_bytes() for path in paths}
        module["build_upgrade_plan"](ROOT, [module["BASE"]])
        self.assertTrue(all(path.read_bytes() == data for path, data in before.items()))

    def test_shared_json_variant_is_verified_without_importing_base(self):
        self.assertTrue(
            module["verify_json_variant"]('JsonType = JSON().with_variant(JSONB(), "postgresql")')
        )
        with self.assertRaises(ValueError):
            module["verify_json_variant"]('JsonType = JSON().with_variant(JSONB(), "mysql")')

    def test_temporary_json_import_avoids_the_project_database_module(self):
        revision = module["CHAIN"][0]
        source = module["reviewed_offline_source"](
            ROOT / f"database/migrations/versions/{revision}.py",
            revision,
            allowed_calls=review["OPERATIONS"],
        )
        self.assertIn("from sqlalchemy.dialects.postgresql import JSONB as JsonType", source)
        self.assertNotIn("from database.base", source)

    def test_unknown_import_or_top_level_execution_is_rejected(self):
        revision = module["CHAIN"][0]
        original = (ROOT / f"database/migrations/versions/{revision}.py").read_text()
        for extra in ("\nimport os\n", "\nraise RuntimeError('must not execute')\n"):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "migration.py"
                path.write_text(original + extra)
                with self.assertRaises(ValueError):
                    module["reviewed_offline_source"](
                        path, revision, allowed_calls=review["OPERATIONS"]
                    )

    def test_wrong_parent_and_unreviewed_operations_are_rejected(self):
        revision = module["CHAIN"][0]
        original = (ROOT / f"database/migrations/versions/{revision}.py").read_text()
        for altered in (
            original.replace(module["BASE"], "wrong_parent"),
            original.replace("op.create_table(", "op.execute(", 1),
        ):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "migration.py"
                path.write_text(altered)
                with self.assertRaises(ValueError):
                    module["reviewed_offline_source"](
                        path, revision, allowed_calls=review["OPERATIONS"]
                    )

    def test_missing_version_update_or_user_data_write_fails_plan_review(self):
        sql = self.plan["sql"]
        broken = sql.replace("UPDATE public.alembic_version", "UPDATE users", 1)
        self.assertFalse(module["assess_range_sql"](broken)["offline_plan_checks_passed"])
        self.assertFalse(
            module["assess_range_sql"](sql + "DROP TABLE users;")["offline_plan_checks_passed"]
        )

    def test_empty_sql_and_wrong_order_fail_plan_review(self):
        self.assertFalse(module["assess_range_sql"]("")["offline_plan_checks_passed"])
        sql = self.plan["sql"].replace(
            "CREATE TABLE tool_execution_ledger", "CREATE TABLE missing_ledger"
        )
        self.assertFalse(module["assess_range_sql"](sql)["offline_plan_checks_passed"])

    def test_generation_is_repeatable(self):
        second = module["build_upgrade_plan"](ROOT, [module["BASE"]])
        self.assertEqual(second["sql"], self.plan["sql"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
