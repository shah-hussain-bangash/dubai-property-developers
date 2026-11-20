"""Transaction/isolation orchestration tests; PostgreSQL behavior is tested separately."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "scripts/maintenance/browser_scratch_acceptance.py"))
planner = runpy.run_path(str(ROOT / "scripts/maintenance/browser_upgrade_plan.py"))
SCHEMA = "step539_" + "a" * 24


class DatabaseError(Exception):
    def __init__(self, state):
        super().__init__("private connection details must never be reported")
        self.sqlstate = state


def setup(
    *, head=None, fail_upgrade=False, wrong_scope=False, stays_readonly=False, deny_write=False
):
    state = {"schema_exists": False, "read_only": True}
    root_transaction = SimpleNamespace(start=AsyncMock())

    async def rollback():
        state["schema_exists"] = False
        state["read_only"] = True

    root_transaction.rollback = AsyncMock(side_effect=rollback)
    savepoints = []

    def transaction(**kwargs):
        if kwargs:
            return root_transaction
        point = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock())
        savepoints.append(point)
        return point

    async def execute(sql, *args):
        if sql == "SET TRANSACTION READ WRITE":
            if deny_write:
                raise DatabaseError("25006")
            state["read_only"] = stays_readonly
        if sql.startswith("CREATE SCHEMA"):
            if state["read_only"]:
                raise DatabaseError("25006")
            state["schema_exists"] = True
        if "CREATE TABLE tool_execution_ledger" in sql and fail_upgrade:
            raise DatabaseError("42501")
        if "SET approval_status='invalid'" in sql or "SET approval_status='approved' WHERE" in sql:
            raise DatabaseError("23514")
        if sql.startswith("INSERT INTO user_external_identities"):
            identifier, _org, user, issuer, subject = args
            if user.int == 5395:
                raise DatabaseError("23503")
            if identifier.int == 5403:
                raise DatabaseError("23505")
            if issuer != "https://accounts.google.com" or not subject.strip():
                raise DatabaseError("23514")
        if sql.startswith("INSERT INTO account_sessions"):
            identifier, _org, user, digest, method, expiry, revoked = args
            if user.int == 5395:
                raise DatabaseError("23503")
            if identifier.int == 5504:
                raise DatabaseError("23505")
            if (
                len(digest) != 64
                or method != "google"
                or expiry <= 0
                or (revoked is not None and revoked < 0)
            ):
                raise DatabaseError("23514")
        return "OK"

    async def fetchval(sql, *args):
        if sql == "SHOW transaction_read_only":
            return "on" if state["read_only"] else "off"
        if sql.startswith("SELECT EXISTS"):
            return state["schema_exists"]
        if sql == "SELECT current_schema()":
            return "public" if wrong_scope else SCHEMA
        if "approval_status IS NULL" in sql:
            return True
        if "SELECT approval_status FROM" in sql:
            return "approved"
        if "SELECT version_num FROM alembic_version" in sql:
            return module["HEAD"]
        if "SELECT is_nullable" in sql:
            return "YES"
        if "SELECT count(*)" in sql:
            return 0
        raise AssertionError("Unexpected catalog query")

    connection = SimpleNamespace(
        transaction=MagicMock(side_effect=transaction),
        execute=AsyncMock(side_effect=execute),
        fetch=AsyncMock(return_value=[{"version_num": head or module["BASE"]}]),
        fetchval=AsyncMock(side_effect=fetchval),
        fetchrow=AsyncMock(
            return_value={
                "approval_status": "pending",
                "approval_decided_by": None,
                "approval_decided_at": None,
            }
        ),
        close=AsyncMock(),
    )
    return AsyncMock(return_value=connection), connection, root_transaction, savepoints


class Tests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = planner["build_upgrade_plan"](ROOT, [planner["BASE"]])["sql"]

    async def test_transaction_envelope_is_removed_and_version_updates_are_scoped(self):
        prepared = module["prepare_scratch_sql"](self.sql, SCHEMA)
        self.assertNotIn("public.alembic_version", prepared)
        self.assertNotIn("BEGIN;", prepared)
        self.assertNotIn("COMMIT;", prepared)
        self.assertEqual(prepared.count(f'UPDATE "{SCHEMA}".alembic_version'), 4)

    async def test_invalid_schema_or_missing_envelope_is_rejected(self):
        for schema in ("public", "step539_bad; DROP SCHEMA public", "step539_" + "z" * 24):
            with self.assertRaises(ValueError):
                module["prepare_scratch_sql"](self.sql, schema)
        with self.assertRaises(ValueError):
            module["prepare_scratch_sql"](self.sql.replace("BEGIN;", "", 1), SCHEMA)

    async def test_public_or_other_qualified_ddl_is_rejected(self):
        for name in ("public.tool_execution_ledger", "other.tool_execution_ledger"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                module["prepare_scratch_sql"](
                    self.sql.replace("CREATE TABLE tool_execution_ledger", "CREATE TABLE " + name),
                    SCHEMA,
                )

    async def test_unreviewed_transaction_or_data_command_is_rejected(self):
        for addition in ("COMMIT;", "DELETE FROM users;", "SET search_path TO public;"):
            with self.subTest(addition=addition), self.assertRaises(ValueError):
                module["prepare_scratch_sql"](
                    self.sql.replace("COMMIT;", addition + "\nCOMMIT;"), SCHEMA
                )

    async def test_success_requires_rollback_schema_removal_and_unchanged_public_head(self):
        connect, connection, transaction, points = setup()
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["acceptance_status"], "passed_and_rolled_back")
        self.assertTrue(result["scratch_read_write_transaction_confirmed"])
        self.assertEqual(len(result["checks"]), 20)
        self.assertTrue(all(result["checks"].values()))
        self.assertTrue(result["scratch_schema_removed"])
        self.assertTrue(result["public_migration_head_unchanged"])
        transaction.rollback.assert_awaited_once()
        connection.transaction.assert_any_call(isolation="repeatable_read", readonly=False)
        self.assertEqual(len(points), 12)
        for point in points:
            point.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_write_override_is_first_statement_and_session_default_stays_readonly(self):
        connect, connection, _transaction, _points = setup()
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertTrue(result["scratch_read_write_transaction_confirmed"])
        self.assertEqual(
            connection.execute.await_args_list[0].args[0], "SET TRANSACTION READ WRITE"
        )
        self.assertEqual(
            connect.await_args.kwargs["server_settings"]["default_transaction_read_only"], "on"
        )
        self.assertEqual(await connection.fetchval("SHOW transaction_read_only"), "on")
        self.assertFalse(
            any(
                "default_transaction_read_only" in call.args[0]
                for call in connection.execute.await_args_list
            )
        )

    async def test_readonly_guard_stops_before_schema_creation(self):
        connect, connection, transaction, _points = setup(stays_readonly=True)
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["acceptance_status"], "unavailable_or_failed")
        self.assertFalse(result["scratch_read_write_transaction_confirmed"])
        self.assertEqual(connection.execute.await_count, 1)
        transaction.rollback.assert_awaited_once()

    async def test_server_write_denial_is_redacted_and_rolled_back(self):
        connect, connection, transaction, _points = setup(deny_write=True)
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["failure_code"], "25006")
        self.assertEqual(result["failure_stage"], "scratch_setup")
        self.assertTrue(result["rollback_confirmed"])
        self.assertNotIn("private connection details", str(result))
        self.assertEqual(connection.execute.await_count, 1)
        transaction.rollback.assert_awaited_once()

    async def test_changed_public_head_aborts_before_temporary_writes(self):
        connect, connection, transaction, _points = setup(head="0007_tool_execution_ledger")
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["acceptance_status"], "database_head_changed")
        connection.execute.assert_not_awaited()
        transaction.start.assert_not_awaited()

    async def test_wrong_search_path_aborts_before_any_table_creation(self):
        connect, connection, transaction, _points = setup(wrong_scope=True)
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["acceptance_status"], "unavailable_or_failed")
        self.assertFalse(
            any("CREATE TABLE" in call.args[0] for call in connection.execute.await_args_list)
        )
        transaction.rollback.assert_awaited_once()

    async def test_upgrade_failure_rolls_back_and_redacts_driver_details(self):
        connect, _connection, transaction, _points = setup(fail_upgrade=True)
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["acceptance_status"], "unavailable_or_failed")
        self.assertEqual(result["failure_stage"], "upgrade_execution")
        self.assertTrue(result["rollback_confirmed"])
        transaction.rollback.assert_awaited_once()
        self.assertNotIn("private connection details", str(result))

    async def test_rollback_failure_never_reports_acceptance(self):
        connect, _connection, transaction, _points = setup()
        transaction.rollback.side_effect = RuntimeError("private cleanup diagnostic")
        result = await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        self.assertEqual(result["acceptance_status"], "rollback_not_confirmed")
        self.assertFalse(result["rollback_confirmed"])

    async def test_missing_configuration_performs_no_connection(self):
        connect, _connection, _transaction, _points = setup()
        result = await module["exercise_upgrade"](None, self.sql, connect=connect, schema=SCHEMA)
        self.assertEqual(result["acceptance_status"], "not_configured")
        connect.assert_not_awaited()

    async def test_unexpected_success_of_invalid_data_returns_false_and_rolls_back(self):
        point = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock())
        connection = SimpleNamespace(transaction=MagicMock(return_value=point), execute=AsyncMock())
        self.assertFalse(
            await module["expect_rejection"](connection, "synthetic statement", (), "23514")
        )
        point.rollback.assert_awaited_once()

    async def test_actual_execute_calls_never_target_public_schema_or_commit(self):
        connect, connection, _transaction, _points = setup()
        await module["exercise_upgrade"](
            "postgresql://fixture", self.sql, connect=connect, schema=SCHEMA
        )
        for call in connection.execute.await_args_list:
            self.assertNotIn("public.", call.args[0])
            self.assertNotIn("COMMIT;", call.args[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
