"""Application upgrade transaction, fresh-backup and failure-boundary contracts."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_database_upgrade.py"))
P = runpy.run_path(str(ROOT / "scripts/maintenance/browser_upgrade_plan.py"))
DSN = "postgresql://user:private_password@localhost/application"


def fixture(
    *, head=None, identity="application", readonly="off", busy=False, backup=True, compatible=True
):
    trace = []
    state = {"head": head or M["BASE"]}

    async def execute(sql):
        trace.append(sql)
        if "CREATE TABLE tool_execution_ledger" in sql:
            state["head"] = M["HEAD"]

    async def fetch(sql, *args):
        if sql == M["TABLES_SQL"]:
            return [
                {"schema_name": "public", "table_name": name}
                for name in ("users", "organizations", "alembic_version")
            ]
        return [{"version_num": state["head"]}] if "SELECT version_num" in sql else []

    async def value(sql):
        if "current_database" in sql:
            return identity
        if "transaction_read_only" in sql:
            return readonly
        if "pg_try_advisory" in sql:
            return not busy
        if "server_version_num" in sql:
            return "160004"
        return "00000001-00000002-1"

    tx = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock(), commit=AsyncMock())
    connection = SimpleNamespace(
        transaction=MagicMock(return_value=tx),
        execute=AsyncMock(side_effect=execute),
        fetch=AsyncMock(side_effect=fetch),
        fetchval=AsyncMock(side_effect=value),
        close=AsyncMock(),
    )

    def write(*args, **kwargs):
        trace.append("fresh_backup")
        return {"archive_validated": backup, "application_account_records_read": True}

    inspector = {
        "COLUMNS_SQL": "columns",
        "CONSTRAINTS_SQL": "constraints",
        "REQUIRED_COLUMNS": {},
        "KEY_CONSTRAINTS": {},
        "CHECK_CONSTRAINTS": {},
        "assess_metadata": lambda *args: {"catalog_metadata_compatible": compatible},
    }
    tools = {"backup_environment": lambda dsn: {}, "write_archive": MagicMock(side_effect=write)}
    return AsyncMock(return_value=connection), connection, tx, inspector, tools, trace


class Tests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = P["build_upgrade_plan"](ROOT, [M["BASE"]])["sql"]

    async def exercise(self, config, dsn=DSN):
        connect, _connection, _tx, inspector, tools, _trace = config
        return await M["apply_upgrade"](
            dsn,
            self.sql,
            Path("private.dump"),
            "dump",
            "restore",
            18,
            inspector,
            tools,
            connect=connect,
        )

    async def test_success_backs_up_under_share_locks_before_schema_lock_and_commit(self):
        config = fixture()
        result = await self.exercise(config)
        _connect, connection, tx, _inspector, _tools, trace = config
        self.assertEqual(result["upgrade_status"], "applied_and_verified")
        self.assertTrue(result["application_migrations_applied_by_this_run"])
        self.assertEqual(result["commit_outcome"], "confirmed")
        self.assertEqual(trace[0], "SET TRANSACTION READ WRITE")
        share = next(i for i, sql in enumerate(trace) if "IN SHARE MODE NOWAIT" in sql)
        exclusive = next(
            i for i, sql in enumerate(trace) if "IN ACCESS EXCLUSIVE MODE NOWAIT" in sql
        )
        ddl = next(i for i, sql in enumerate(trace) if "CREATE TABLE tool_execution_ledger" in sql)
        self.assertLess(share, trace.index("fresh_backup"))
        self.assertLess(trace.index("fresh_backup"), exclusive)
        self.assertLess(exclusive, ddl)
        connection.transaction.assert_called_once_with(isolation="read_committed", readonly=False)
        tx.commit.assert_awaited_once()
        tx.rollback.assert_not_awaited()

    async def test_failed_backup_rolls_back_without_migrations(self):
        config = fixture(backup=False)
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "fresh_backup_failed")
        self.assertFalse(any("CREATE TABLE tool_execution_ledger" in sql for sql in config[-1]))
        config[2].rollback.assert_awaited_once()

    async def test_busy_advisory_lock_does_not_start_backup(self):
        config = fixture(busy=True)
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "another_upgrade_in_progress")
        config[4]["write_archive"].assert_not_called()

    async def test_changed_head_stops_upgrade(self):
        config = fixture(head="private unexpected revision")
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "database_head_changed")
        self.assertNotIn("private unexpected revision", str(result))
        config[4]["write_archive"].assert_not_called()

    async def test_current_head_checks_metadata_without_reapplying(self):
        config = fixture(head=M["HEAD"])
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "already_current")
        self.assertFalse(result["application_migrations_applied_by_this_run"])
        config[4]["write_archive"].assert_not_called()
        config[2].commit.assert_not_awaited()

    async def test_wrong_database_identity_prevents_transaction(self):
        config = fixture(identity="other")
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "failed")
        config[2].start.assert_not_awaited()

    async def test_readonly_guard_stops_before_locking(self):
        config = fixture(readonly="on")
        result = await self.exercise(config)
        self.assertFalse(result["application_migrations_applied_by_this_run"])
        self.assertEqual(config[1].execute.await_count, 1)
        config[2].rollback.assert_awaited_once()

    async def test_lock_conflict_sanitized_and_no_backup(self):
        config = fixture()
        original = config[1].execute.side_effect

        async def execute(sql):
            if sql.startswith("LOCK TABLE"):
                error = RuntimeError("private table and connection details")
                error.sqlstate = "55P03"
                raise error
            return await original(sql)

        config[1].execute.side_effect = execute
        result = await self.exercise(config)
        self.assertEqual(result["failure_code"], "55P03")
        self.assertNotIn("private table", str(result))
        config[4]["write_archive"].assert_not_called()

    async def test_schema_mismatch_rolls_back_before_commit(self):
        config = fixture(compatible=False)
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "schema_verification_failed")
        config[2].commit.assert_not_awaited()
        config[2].rollback.assert_awaited_once()

    async def test_commit_failure_marks_outcome_unknown(self):
        config = fixture()
        config[2].commit.side_effect = RuntimeError("private commit failure")
        result = await self.exercise(config)
        self.assertEqual(result["commit_outcome"], "unknown")
        self.assertIsNone(result["application_migrations_applied_by_this_run"])

    async def test_rollback_failure_is_not_reported_as_success(self):
        config = fixture(backup=False)
        config[2].rollback.side_effect = RuntimeError("private rollback failure")
        result = await self.exercise(config)
        self.assertEqual(result["upgrade_status"], "rollback_not_confirmed")
        self.assertFalse(result["rollback_confirmed"])

    async def test_temporary_destination_rejected(self):
        config = fixture()
        result = await self.exercise(config, "postgresql://u:p@localhost/step544_" + "a" * 24)
        self.assertEqual(result["upgrade_status"], "failed")
        config[0].assert_not_awaited()

    async def test_identifiers_are_quoted_not_interpolated_as_commands(self):
        self.assertEqual(
            M["quote_identifier"]('x"; DROP TABLE users;--'), '"x""; DROP TABLE users;--"'
        )
        with self.assertRaises(ValueError):
            M["quote_identifier"]("bad\x00name")

    async def test_missing_or_system_tables_rejected(self):
        for rows in ([], [{"schema_name": "pg_catalog", "table_name": "users"}]):
            with self.assertRaises(ValueError):
                M["lock_targets"](rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
