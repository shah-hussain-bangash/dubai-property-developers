"""Offline contracts for backup prerequisites, never a real backup."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_backup_readiness.py"))
TOOLS = [{"dump_major": 18, "restore_major": 18}]


def fixture(*, readonly="on", head=None, version="160004"):
    tx = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock())

    async def value(sql):
        return readonly if sql == "SHOW transaction_read_only" else version

    connection = SimpleNamespace(
        transaction=MagicMock(return_value=tx),
        execute=AsyncMock(),
        fetchval=AsyncMock(side_effect=value),
        fetch=AsyncMock(return_value=[{"version_num": head or M["BASE"]}]),
        fetchrow=AsyncMock(
            return_value=dict.fromkeys(
                ("tables_readable", "sequences_readable", "row_security_compatible"), True
            )
        ),
        close=AsyncMock(),
    )
    return AsyncMock(return_value=connection), connection, tx


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_relation_specific_privilege_functions_are_case_guarded(self):
        sql = M["PRIVILEGES_SQL"]
        self.assertIn("CASE WHEN c.relkind IN ('r','p','m')", sql)
        self.assertIn("THEN NOT has_table_privilege(c.oid, 'SELECT') ELSE false END", sql)
        self.assertIn("CASE WHEN c.relkind='S'", sql)
        self.assertIn("THEN NOT has_sequence_privilege(c.oid, 'SELECT') ELSE false END", sql)

    async def test_wrong_object_error_records_only_approved_sqlstate(self):
        connect, connection, _tx = fixture()
        error = RuntimeError("private credentials and relation name")
        error.sqlstate = "42809"
        connection.fetchrow.side_effect = error
        result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
        self.assertEqual(result["failure_code"], "42809")
        self.assertNotIn("private credentials", str(result))
        self.assertTrue(result["rollback_confirmed"])

    async def test_pass_is_prerequisites_only(self):
        connect, connection, tx = fixture()
        result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
        self.assertEqual(result["backup_readiness_status"], "backup_prerequisites_passed")
        self.assertEqual(len(result["checks"]), 4)
        self.assertTrue(result["rollback_confirmed"])
        for key in (
            "backup_created",
            "restore_tested",
            "upgrade_authorized",
            "application_account_records_read",
            "migrations_applied",
        ):
            self.assertFalse(result[key])
        connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
        tx.rollback.assert_awaited_once()

    async def test_readonly_guard_and_changed_head_stop_queries(self):
        for kwargs, expected in (
            ({"readonly": "off"}, "read_only_guard_failed"),
            ({"head": "private revision"}, "database_head_changed"),
        ):
            connect, connection, _tx = fixture(**kwargs)
            result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
            self.assertEqual(result["backup_readiness_status"], expected)
            self.assertNotIn("private revision", str(result))
            connection.fetchrow.assert_not_awaited()

    async def test_older_mismatched_or_missing_clients_block(self):
        for tools in (
            [],
            [{"dump_major": 15, "restore_major": 15}],
            [{"dump_major": 18, "restore_major": 17}],
        ):
            connect, _connection, _tx = fixture()
            result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=tools)
            self.assertEqual(result["backup_readiness_status"], "blocked")

    async def test_unreadable_tables_sequences_or_rls_blocks(self):
        for key in ("tables_readable", "sequences_readable", "row_security_compatible"):
            for value in (False, None, "private value"):
                connect, connection, _tx = fixture()
                connection.fetchrow.return_value[key] = value
                result = await M["inspect_backup_readiness"](
                    "fixture", connect=connect, tools=TOOLS
                )
                self.assertEqual(result["backup_readiness_status"], "blocked")

    async def test_server_version_is_sanitized(self):
        connect, _connection, _tx = fixture(version="private server detail")
        result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
        self.assertEqual(result["backup_readiness_status"], "unavailable")
        self.assertNotIn("private server detail", str(result))

    async def test_driver_failure_is_sanitized_and_closed(self):
        connect, connection, tx = fixture()
        connection.fetchrow.side_effect = RuntimeError("private credentials")
        result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
        self.assertNotIn("private credentials", str(result))
        self.assertEqual(result["backup_readiness_status"], "unavailable")
        tx.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_cleanup_failures_block(self):
        for target in ("rollback", "close"):
            connect, connection, tx = fixture()
            mock = tx.rollback if target == "rollback" else connection.close
            mock.side_effect = RuntimeError("private cleanup")
            result = await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
            self.assertNotEqual(result["backup_readiness_status"], "backup_prerequisites_passed")

    async def test_no_configuration_does_not_connect(self):
        connect, _connection, _tx = fixture()
        await M["inspect_backup_readiness"](None, connect=connect, tools=TOOLS)
        connect.assert_not_awaited()

    async def test_no_dump_restore_or_user_queries_are_executed(self):
        connect, connection, _tx = fixture()
        await M["inspect_backup_readiness"]("fixture", connect=connect, tools=TOOLS)
        self.assertEqual(connection.fetchrow.await_args.args[0], M["PRIVILEGES_SQL"])
        self.assertEqual(
            [c.args[0] for c in connection.execute.await_args_list],
            [
                "SET LOCAL statement_timeout = '5s'",
                "SET LOCAL lock_timeout = '2s'",
            ],
        )
        self.assertNotIn("FROM public.users", M["PRIVILEGES_SQL"])

    async def test_version_probe_uses_only_version_flag_and_drops_raw_output(self):
        run = MagicMock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout="pg_dump (PostgreSQL) 18.0\n"),
                SimpleNamespace(returncode=0, stdout="pg_restore (PostgreSQL) 18.0\n"),
            ]
        )
        with patch.object(Path, "is_file", return_value=True):
            tools = M["probe_tools"]([(Path("pg_dump.exe"), Path("pg_restore.exe"))], run=run)
        self.assertEqual(tools, TOOLS)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][1:], ["--version"])

    async def test_probe_rejects_mismatch_failures_and_untrusted_output(self):
        for output, code in (("private diagnostic", 0), ("pg_dump (PostgreSQL) 18.0", 1)):
            run = MagicMock(return_value=SimpleNamespace(returncode=code, stdout=output))
            with patch.object(Path, "is_file", return_value=True):
                self.assertEqual(M["probe_tools"]([(Path("dump"), Path("restore"))], run=run), [])

    async def test_missing_tools_are_not_executed(self):
        run = MagicMock()
        with patch.object(Path, "is_file", return_value=False):
            self.assertEqual(M["probe_tools"]([(Path("dump"), Path("restore"))], run=run), [])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
