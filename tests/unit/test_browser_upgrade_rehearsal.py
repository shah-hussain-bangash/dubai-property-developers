"""Transactional account-upgrade checks on restored disposable databases."""

import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_upgrade_rehearsal.py"))
PLANNER = runpy.run_path(str(ROOT / "scripts/maintenance/browser_upgrade_plan.py"))
RESTORE_TESTS = runpy.run_path(str(ROOT / "tests/unit/test_browser_restore_rehearsal.py"))
NAME = "step544_" + "a" * 24
DSN = RESTORE_TESTS["DSN"]
ENV = RESTORE_TESTS["ENV"]


def fixture(*, name=NAME, readonly="off", metadata=True, legacy=True):
    state = {"head": M["BASE"]}

    async def execute(sql):
        if "CREATE TABLE tool_execution_ledger" in sql:
            state["head"] = M["HEAD"]

    async def fetch(sql, *args):
        return [{"version_num": state["head"]}] if "version_num" in sql else []

    async def value(sql):
        if sql == "SELECT current_database()":
            return name
        if sql == "SHOW transaction_read_only":
            return readonly
        return legacy if "approval_status IS NOT NULL" in sql else True

    tx = SimpleNamespace(start=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    connection = SimpleNamespace(
        transaction=MagicMock(return_value=tx),
        execute=AsyncMock(side_effect=execute),
        fetch=AsyncMock(side_effect=fetch),
        fetchval=AsyncMock(side_effect=value),
    )
    inspector = {
        "COLUMNS_SQL": "columns",
        "CONSTRAINTS_SQL": "constraints",
        "REQUIRED_COLUMNS": {},
        "KEY_CONSTRAINTS": {},
        "CHECK_CONSTRAINTS": {},
        "assess_metadata": lambda *args: {"catalog_metadata_compatible": metadata},
    }
    return connection, tx, inspector


class Tests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = PLANNER["build_upgrade_plan"](ROOT, [M["BASE"]])["sql"]

    async def test_upgrade_commits_only_after_all_checks(self):
        connection, tx, inspector = fixture()
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertEqual(result["upgrade_status"], "passed")
        self.assertTrue(all(result["checks"].values()))
        self.assertTrue(result["committed_on_copy"])
        self.assertFalse(result["application_database_migrations_applied"])
        self.assertEqual(
            connection.execute.await_args_list[0].args[0], "SET TRANSACTION READ WRITE"
        )
        tx.commit.assert_awaited_once()
        tx.rollback.assert_not_awaited()

    async def test_source_database_identity_prevents_ddl(self):
        connection, tx, inspector = fixture(name="source")
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertEqual(result["upgrade_status"], "failed")
        tx.start.assert_not_awaited()
        connection.execute.assert_not_awaited()

    async def test_unsafe_copy_name_rejected(self):
        connection, _tx, inspector = fixture()
        with self.assertRaises(ValueError):
            await M["verify_upgrade"](connection, "source", self.sql, inspector)

    async def test_readonly_guard_rolls_back_without_ddl(self):
        connection, tx, inspector = fixture(readonly="on")
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertEqual(result["upgrade_status"], "failed")
        self.assertEqual(connection.execute.await_count, 1)
        tx.rollback.assert_awaited_once()

    async def test_metadata_mismatch_rolls_back(self):
        connection, tx, inspector = fixture(metadata=False)
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertEqual(result["upgrade_status"], "verification_failed")
        tx.commit.assert_not_awaited()
        tx.rollback.assert_awaited_once()

    async def test_legacy_account_changes_block_commit(self):
        connection, tx, inspector = fixture(legacy=False)
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertFalse(result["checks"]["legacy_approval_fields_preserved"])
        tx.commit.assert_not_awaited()

    async def test_execution_failure_is_redacted_and_rolls_back(self):
        connection, tx, inspector = fixture()
        connection.execute.side_effect = RuntimeError("private credentials")
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertNotIn("private credentials", str(result))
        self.assertEqual(result["upgrade_status"], "failed")
        tx.rollback.assert_awaited_once()

    async def test_rollback_failure_blocks_success(self):
        connection, tx, inspector = fixture(metadata=False)
        tx.rollback.side_effect = RuntimeError("private rollback")
        result = await M["verify_upgrade"](connection, NAME, self.sql, inspector)
        self.assertEqual(result["upgrade_status"], "rollback_not_confirmed")

    async def test_inner_commit_and_data_commands_rejected(self):
        for addition in ("COMMIT;", "DELETE FROM users;", "INSERT INTO users VALUES(1);"):
            with self.assertRaises(ValueError):
                M["transaction_body"](self.sql.replace("COMMIT;", addition + "\nCOMMIT;"))

    async def test_missing_envelope_rejected(self):
        with self.assertRaises(ValueError):
            M["transaction_body"](self.sql.replace("BEGIN;", "", 1))

    async def test_restore_lifecycle_removes_copy_after_upgrade(self):
        await self.lifecycle("passed", "upgraded_verified_and_removed")

    async def test_restore_lifecycle_removes_copy_after_upgrade_failure(self):
        await self.lifecycle("verification_failed", "copy_upgrade_failed")

    async def lifecycle(self, status, expected):
        with TemporaryDirectory() as folder:
            archive = Path(folder) / "backup.dump"
            archive.write_bytes(b"PGDMP synthetic archive")
            import hashlib

            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            connect, _source, _control, target = RESTORE_TESTS["fixture"]()
            target.fetchval.return_value = NAME
            check = AsyncMock(return_value={"upgrade_status": status})
            with patch.dict(M["rehearse_upgrade"].__globals__, {"verify_upgrade": check}):
                result = await M["rehearse_upgrade"](
                    DSN,
                    archive,
                    digest,
                    "restore",
                    "psql",
                    ENV,
                    self.sql,
                    {},
                    connect=connect,
                    run=RESTORE_TESTS["process"](),
                    name=NAME,
                )
            self.assertEqual(result["upgrade_rehearsal_status"], expected)
            self.assertTrue(result["temporary_database_removed"])
            self.assertTrue(result["source_head_unchanged"])
            self.assertTrue(result["archive_unchanged"])
            check.assert_awaited_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
