"""Backup orchestration contracts using synthetic bytes and fake processes."""

import os
import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_database_backup.py"))
DSN = "postgresql://example_user:private_password@localhost:5432/example"
SNAPSHOT = "00000003-0000001B-1"
TOC = "\n".join(
    f"{i}; 0 1 TABLE DATA public {table} example_user"
    for i, table in enumerate(("users", "organizations", "alembic_version"), 1)
)


def process(*, fail=None, invalid_header=False, toc=TOC):
    def run(args, **kwargs):
        if "--format=custom" in args:
            kwargs["stdout"].write(b"bad" if invalid_header else b"PGDMP synthetic archive")
            return SimpleNamespace(returncode=1 if fail == "dump" else 0)
        if "--list" in args:
            return SimpleNamespace(returncode=1 if fail == "list" else 0, stdout=toc)
        return SimpleNamespace(returncode=1 if fail == "decode" else 0)

    return MagicMock(side_effect=run)


def fixture(*, readonly="on", head=None):
    async def value(sql):
        return readonly if sql == "SHOW transaction_read_only" else SNAPSHOT

    tx = SimpleNamespace(start=AsyncMock(), rollback=AsyncMock())
    connection = SimpleNamespace(
        transaction=MagicMock(return_value=tx),
        fetchval=AsyncMock(side_effect=value),
        fetch=AsyncMock(return_value=[{"version_num": head or M["BASE"]}]),
        close=AsyncMock(),
    )
    return AsyncMock(return_value=connection), connection, tx


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "backup.dump"

    def archive(self, run):
        return M["write_archive"](
            self.path, Path("pg_dump"), Path("pg_restore"), {}, SNAPSHOT, run=run
        )

    async def test_success_is_consistent_archive_not_restore_or_migration(self):
        connect, connection, tx = fixture()
        run = process()
        result = await M["backup_database"](
            DSN, self.path, "dump", "restore", connect=connect, run=run
        )
        self.assertEqual(result["backup_status"], "archive_created_and_validated")
        self.assertTrue(result["rollback_confirmed"])
        self.assertTrue(result["application_account_records_read"])
        self.assertFalse(result["restore_tested"])
        self.assertFalse(result["migrations_applied"])
        self.assertEqual(len(result["archive_sha256"]), 64)
        connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
        tx.rollback.assert_awaited_once()
        self.assertIn("--snapshot=" + SNAPSHOT, run.call_args_list[0].args[0])

    async def test_credentials_only_in_child_environment_not_argv_or_evidence(self):
        connect, _connection, _tx = fixture()
        run = process()
        result = await M["backup_database"](
            DSN, self.path, "dump", "restore", connect=connect, run=run
        )
        self.assertNotIn("private_password", str(result))
        for call in run.call_args_list:
            self.assertNotIn("private_password", str(call.args[0]))
            self.assertNotIn("--dbname", str(call.args[0]))
        self.assertEqual(run.call_args_list[0].kwargs["env"]["PGPASSWORD"], "private_password")
        for call in run.call_args_list[1:]:
            self.assertNotIn("PGPASSWORD", call.kwargs["env"])
            self.assertNotIn("PGDATABASE", call.kwargs["env"])

    async def test_environment_overrides_inherited_libpq_configuration(self):
        with patch.dict(
            os.environ,
            {"PGSERVICE": "private_service", "PGOPTIONS": "unsafe", "DATABASE_URL": "private"},
        ):
            env = M["backup_environment"](DSN)
        self.assertNotIn("PGSERVICE", env)
        self.assertNotIn("DATABASE_URL", env)
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"])

    async def test_changed_head_or_readonly_failure_never_starts_dump(self):
        for kwargs in ({"head": "private revision"}, {"readonly": "off"}):
            connect, _connection, tx = fixture(**kwargs)
            run = process()
            result = await M["backup_database"](
                DSN, self.path, "dump", "restore", connect=connect, run=run
            )
            self.assertFalse(result["pg_dump_connection_attempted"])
            run.assert_not_called()
            tx.rollback.assert_awaited_once()

    async def test_existing_archive_is_preserved(self):
        self.path.write_bytes(b"preserve")
        run = process()
        result = self.archive(run)
        self.assertEqual(self.path.read_bytes(), b"preserve")
        self.assertFalse(result["backup_created"])
        run.assert_not_called()

    async def test_dump_failure_preserves_partial_and_does_not_validate(self):
        run = process(fail="dump")
        result = self.archive(run)
        self.assertFalse(result["archive_validated"])
        self.assertEqual(result["failure_stage"], "pg_dump")
        self.assertTrue(self.path.exists())
        self.assertEqual(run.call_count, 1)

    async def test_bad_header_blocks_inventory(self):
        run = process(invalid_header=True)
        result = self.archive(run)
        self.assertEqual(result["failure_stage"], "archive_header")
        self.assertEqual(run.call_count, 1)

    async def test_missing_required_table_data_blocks_validation(self):
        result = self.archive(process(toc="private contents"))
        self.assertEqual(result["failure_stage"], "archive_inventory")
        self.assertNotIn("private contents", str(result))

    async def test_archive_decode_failure_blocks_validation(self):
        result = self.archive(process(fail="decode"))
        self.assertFalse(result["archive_validated"])
        self.assertEqual(result["failure_stage"], "archive_decode")

    async def test_archive_timeout_is_redacted(self):
        run = MagicMock(side_effect=TimeoutError("private connection detail"))
        result = self.archive(run)
        self.assertFalse(result["archive_validated"])
        self.assertNotIn("private connection detail", str(result))

    async def test_invalid_snapshot_rejected_before_file_creation(self):
        with self.assertRaises(ValueError):
            M["write_archive"](
                self.path, "dump", "restore", {}, "untrusted snapshot", run=process()
            )
        self.assertFalse(self.path.exists())

    async def test_cleanup_failure_blocks_success(self):
        connect, _connection, tx = fixture()
        tx.rollback.side_effect = RuntimeError("private diagnostic")
        result = await M["backup_database"](
            DSN, self.path, "dump", "restore", connect=connect, run=process()
        )
        self.assertEqual(result["backup_status"], "rollback_not_confirmed")

    async def test_configuration_failure_does_not_connect(self):
        connect, _connection, _tx = fixture()
        result = await M["backup_database"](
            "sqlite:///invalid", self.path, "dump", "restore", connect=connect
        )
        self.assertEqual(result["backup_status"], "unavailable")
        connect.assert_not_awaited()

    async def test_missing_dsn_does_not_create_file(self):
        result = await M["backup_database"](None, self.path, "dump", "restore")
        self.assertFalse(result["backup_created"])
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
