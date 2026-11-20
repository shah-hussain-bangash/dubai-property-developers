"""Offline contracts for read-only migration preflight."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_upgrade_preflight.py"))


def fixture(*, readonly="on", head=None):
    tx = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock())
    row = {**dict.fromkeys(M["REQUIRED"], True), **dict.fromkeys(M["ABSENT"], False)}
    connection = SimpleNamespace(
        transaction=MagicMock(return_value=tx),
        execute=AsyncMock(),
        fetchval=AsyncMock(return_value=readonly),
        fetch=AsyncMock(return_value=[{"version_num": head or M["BASE"]}]),
        fetchrow=AsyncMock(return_value=row),
        close=AsyncMock(),
    )
    return AsyncMock(return_value=connection), connection, tx


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_passing_catalog_still_does_not_authorize_activation_or_claim_data_compatibility(
        self,
    ):
        connect, connection, tx = fixture()
        result = await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(result["preflight_status"], "catalog_preflight_passed")
        self.assertEqual(len(result["checks"]), 12)
        self.assertTrue(result["rollback_confirmed"])
        self.assertFalse(result["application_account_records_read"])
        self.assertFalse(result["existing_data_migration_compatibility_proven"])
        self.assertFalse(result["migrations_applied"])
        self.assertFalse(result["live_activation_ready"])
        connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
        tx.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_read_only_guard_stops_before_queries(self):
        connect, connection, tx = fixture(readonly="off")
        result = await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(result["preflight_status"], "read_only_guard_failed")
        connection.fetch.assert_not_awaited()
        connection.fetchrow.assert_not_awaited()
        connection.execute.assert_not_awaited()
        tx.rollback.assert_awaited_once()

    async def test_changed_head_stops_before_catalog(self):
        connect, connection, _tx = fixture(head="private unexpected revision")
        result = await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(result["preflight_status"], "database_head_changed")
        self.assertNotIn("private unexpected", str(result))
        connection.fetchrow.assert_not_awaited()

    async def test_each_missing_privilege_or_baseline_blocks(self):
        for key in M["REQUIRED"]:
            with self.subTest(key=key):
                connect, connection, _tx = fixture()
                connection.fetchrow.return_value[key] = False
                result = await M["inspect_upgrade"]("fixture", connect=connect)
                self.assertEqual(result["preflight_status"], "blocked")
                self.assertFalse(result["checks"][key])

    async def test_each_collision_or_other_lock_blocks(self):
        for key in M["ABSENT"]:
            with self.subTest(key=key):
                connect, connection, _tx = fixture()
                connection.fetchrow.return_value[key] = True
                result = await M["inspect_upgrade"]("fixture", connect=connect)
                self.assertEqual(result["preflight_status"], "blocked")

    async def test_unknown_or_missing_catalog_values_fail_closed(self):
        self.assertFalse(any(M["assess_catalog"]({}).values()))
        for key in (*M["REQUIRED"], *M["ABSENT"]):
            self.assertFalse(M["assess_catalog"]({key: "private value"})[key])

    async def test_driver_failure_redacts_and_closes(self):
        connect, connection, tx = fixture()
        connection.fetchrow.side_effect = RuntimeError("private credentials")
        result = await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(result["preflight_status"], "unavailable")
        self.assertEqual(result["failure_stage"], "catalog_checks")
        self.assertNotIn("private credentials", str(result))
        tx.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_rollback_failure_blocks_acceptance(self):
        connect, _connection, tx = fixture()
        tx.rollback.side_effect = RuntimeError("private rollback")
        result = await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(result["preflight_status"], "rollback_not_confirmed")
        self.assertFalse(result["rollback_confirmed"])

    async def test_close_failure_blocks_acceptance(self):
        connect, connection, _tx = fixture()
        connection.close.side_effect = RuntimeError("private close")
        result = await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(result["preflight_status"], "connection_cleanup_not_confirmed")

    async def test_missing_dsn_does_not_connect(self):
        connect, _connection, _tx = fixture()
        result = await M["inspect_upgrade"](None, connect=connect)
        self.assertFalse(result["connection_attempted"])
        connect.assert_not_awaited()

    async def test_only_timeout_settings_are_executed(self):
        connect, connection, _tx = fixture()
        await M["inspect_upgrade"]("fixture", connect=connect)
        self.assertEqual(
            [call.args[0] for call in connection.execute.await_args_list],
            [
                "SET LOCAL statement_timeout = '5s'",
                "SET LOCAL lock_timeout = '2s'",
            ],
        )
        self.assertEqual(
            connection.fetch.await_args.args[0], "SELECT version_num FROM public.alembic_version"
        )
        self.assertEqual(connection.fetchrow.await_args.args[0], M["CATALOG_SQL"])
        for forbidden in (
            "FROM public.users",
            "FROM public.organizations",
            "SELECT *",
            "pg_stat_activity",
        ):
            self.assertNotIn(forbidden, M["CATALOG_SQL"])

    async def test_sql_requires_both_version_permissions_and_uses_parameters_for_collisions(self):
        sql = M["CATALOG_SQL"]
        self.assertIn("has_table_privilege('public.alembic_version', 'SELECT')", sql)
        self.assertIn("AND has_table_privilege('public.alembic_version', 'UPDATE')", sql)
        self.assertNotIn("SELECT,UPDATE", sql)
        self.assertTrue(all(f"${i}::text[]" in sql for i in (1, 2, 3)))
        self.assertIn("NOT c.relispartition", sql)
        self.assertIn("k.conkey=ARRAY[a.attnum]", sql)


if __name__ == "__main__":
    unittest.main(verbosity=2)
