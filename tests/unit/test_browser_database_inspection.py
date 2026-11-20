"""Read-only inspection contracts with a fake asyncpg connection."""

import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "scripts/maintenance/browser_database_inspection.py"))
DSN = "postgresql+asyncpg://fixture:private-password-never-recorded@localhost/project"


def metadata():
    columns = []
    for table, names in module["REQUIRED_COLUMNS"].items():
        for name in names:
            kind, length = "character varying", 255
            if name in {"id", "organization_id", "user_id", "role_id", "approval_decided_by"}:
                kind, length = "uuid", None
            elif name == "is_active":
                kind, length = "boolean", None
            elif name in {"issued_at", "expires_at", "revoked_at", "approval_decided_at"}:
                kind, length = "timestamp with time zone", None
            elif name == "details":
                kind, length = "jsonb", None
            elif name == "token_digest":
                length = 64
            elif name in {"auth_method", "approval_status"}:
                length = 16
            nullable = name in {
                "approval_status",
                "approval_decided_by",
                "approval_decided_at",
                "revoked_at",
                "password_hash",
            } or (table == "audit_logs" and name == "resource_id")
            columns.append(
                dict(
                    table_name=table,
                    column_name=name,
                    data_type=kind,
                    character_maximum_length=length,
                    is_nullable="YES" if nullable else "NO",
                )
            )
    columns.append(
        dict(
            table_name="alembic_version",
            column_name="version_num",
            data_type="character varying",
            character_maximum_length=32,
            is_nullable="NO",
        )
    )
    constraints = []
    for name, (table, kind, keys, target, references) in module["KEY_CONSTRAINTS"].items():
        constraints.append(
            dict(
                name=name,
                table_name=table,
                kind=kind,
                validated=True,
                columns=keys,
                referenced_schema="public" if target else None,
                referenced_table=target,
                referenced_columns=references,
                delete_action="r" if name == "fk_users_approval_decided_by_users" else "c",
            )
        )
    constraints.extend(
        dict(name=name, table_name=table, kind="c", validated=True)
        for name, table in module["CHECK_CONSTRAINTS"].items()
    )
    return columns, constraints


def setup(*, readonly="on"):
    columns, constraints = metadata()
    transaction = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock())
    connection = SimpleNamespace(
        transaction=MagicMock(return_value=transaction),
        close=AsyncMock(),
        fetchval=AsyncMock(return_value=readonly),
        fetch=AsyncMock(
            side_effect=[
                columns,
                constraints,
                [{"version_num": module["EXPECTED_HEAD"]}],
            ]
        ),
    )
    return AsyncMock(return_value=connection), connection, transaction


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_readonly_repeatable_read_is_confirmed_before_catalog_queries(self):
        connect, connection, transaction = setup()
        result = await module["inspect_database"](DSN, connect=connect)
        self.assertEqual(result["inspection_status"], "completed")
        self.assertTrue(result["read_only_transaction_confirmed"])
        connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
        transaction.start.assert_awaited_once()
        transaction.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()
        self.assertEqual(
            connect.await_args.kwargs["server_settings"]["default_transaction_read_only"], "on"
        )

    async def test_metadata_match_does_not_claim_behavior_or_activation_verified(self):
        columns, constraints = metadata()
        result = module["assess_metadata"](columns, constraints, [module["EXPECTED_HEAD"]])
        self.assertTrue(result["catalog_metadata_compatible"])
        self.assertFalse(result["constraint_behavior_verified"])
        self.assertFalse(result["check_constraint_definitions_verified"])
        self.assertFalse(result["live_activation_ready"])

    async def test_readonly_guard_failure_stops_all_catalog_queries(self):
        connect, connection, transaction = setup(readonly="off")
        result = await module["inspect_database"](DSN, connect=connect)
        self.assertEqual(result["inspection_status"], "read_only_guard_failed")
        connection.fetch.assert_not_awaited()
        transaction.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_missing_or_unsupported_url_never_connects(self):
        for value in (
            None,
            "",
            "sqlite:///file.db",
            "postgresql+asyncpg://localhost",
            DSN + "?options=unsafe",
        ):
            with self.subTest(value=value):
                connect, _connection, _transaction = setup()
                result = await module["inspect_database"](value, connect=connect)
                self.assertFalse(result["connection_attempted"])
                connect.assert_not_awaited()

    async def test_driver_errors_never_expose_credentials(self):
        connect = AsyncMock(side_effect=RuntimeError(DSN))
        result = await module["inspect_database"](DSN, connect=connect)
        self.assertEqual(result["inspection_status"], "unavailable")
        self.assertEqual(result["failure_stage"], "connect")
        self.assertNotIn("private-password-never-recorded", json.dumps(result))
        self.assertNotIn(DSN, json.dumps(result))

    async def test_catalog_query_failure_rolls_back_and_closes(self):
        connect, connection, transaction = setup()
        connection.fetch.side_effect = RuntimeError("private server details")
        result = await module["inspect_database"](DSN, connect=connect)
        self.assertEqual(result["failure_stage"], "catalog_query")
        self.assertNotIn("private server details", json.dumps(result))
        transaction.rollback.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_missing_auth_tables_and_old_migration_head_are_reported(self):
        columns, constraints = metadata()
        columns = [
            row
            for row in columns
            if row["table_name"] not in {"account_sessions", "user_external_identities"}
        ]
        result = module["assess_metadata"](columns, constraints, ["0008_tool_request_fingerprint"])
        self.assertFalse(result["catalog_metadata_compatible"])
        self.assertIn("account_sessions", result["missing_columns"])
        self.assertFalse(result["expected_migration_head_applied"])

    async def test_absent_version_table_is_reported_without_querying_it(self):
        connect, connection, _transaction = setup()
        columns, constraints = metadata()
        connection.fetch.side_effect = [
            [row for row in columns if row["table_name"] != "alembic_version"],
            constraints,
        ]
        result = await module["inspect_database"](DSN, connect=connect)
        self.assertEqual(result["metadata"]["applied_migration_heads"], [])
        self.assertEqual(connection.fetch.await_count, 2)

    async def test_unknown_migration_values_are_not_echoed(self):
        columns, constraints = metadata()
        result = module["assess_metadata"](
            columns, constraints, ["private-value-in-untrusted-version-row"]
        )
        self.assertEqual(result["applied_migration_heads"], ["unrecognized"])
        self.assertNotIn("private-value-in-untrusted-version-row", json.dumps(result))

    async def test_digest_type_length_and_nullability_mismatch_is_reported(self):
        for field, value in (
            ("data_type", "text"),
            ("character_maximum_length", 32),
            ("is_nullable", "YES"),
        ):
            columns, constraints = metadata()
            row = next(
                row
                for row in columns
                if row["table_name"] == "account_sessions" and row["column_name"] == "token_digest"
            )
            row[field] = value
            result = module["assess_metadata"](columns, constraints, [module["EXPECTED_HEAD"]])
            self.assertEqual(result["column_metadata"]["account_sessions.token_digest"], "mismatch")

    async def test_wrong_tenant_foreign_key_or_reference_schema_is_rejected(self):
        for field, value in (
            ("referenced_columns", ["id"]),
            ("referenced_schema", "other"),
            ("delete_action", "n"),
        ):
            columns, constraints = metadata()
            row = next(
                row for row in constraints if row["name"] == "fk_account_session_tenant_user"
            )
            row[field] = value
            result = module["assess_metadata"](columns, constraints, [module["EXPECTED_HEAD"]])
            self.assertEqual(
                result["key_constraints"]["fk_account_session_tenant_user"], "missing_or_mismatch"
            )

    async def test_missing_or_unvalidated_check_constraint_is_reported(self):
        columns, constraints = metadata()
        next(row for row in constraints if row["name"] == "ck_account_session_expiry")[
            "validated"
        ] = False
        result = module["assess_metadata"](columns, constraints, [module["EXPECTED_HEAD"]])
        self.assertEqual(
            result["check_constraints"]["ck_account_session_expiry"], "missing_or_mismatch"
        )

    async def test_queries_are_limited_to_metadata_and_migration_version(self):
        connect, connection, _transaction = setup()
        await module["inspect_database"](DSN, connect=connect)
        for call in connection.fetch.await_args_list:
            query = call.args[0].lower().strip()
            self.assertTrue(query.startswith("select"))
            self.assertNotIn("from public.users", query)
            self.assertNotIn("from users", query)
        self.assertEqual(connection.fetchval.await_args.args[0], "SHOW transaction_read_only")

    async def test_url_conversion_preserves_password_without_logging_it(self):
        self.assertEqual(
            module["connect_dsn"](DSN), DSN.replace("postgresql+asyncpg:", "postgresql:", 1)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
