"""Restore rehearsal guards with synthetic SQL, archives and database connections."""

import hashlib
import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "scripts/maintenance/browser_restore_rehearsal.py"))
ENV = runpy.run_path(str(ROOT / "scripts/maintenance/browser_database_backup.py"))[
    "backup_environment"
]
NAME = "step543_" + "a" * 24
DSN = "postgresql://user:private_password@localhost/source"
HEADER = b"--\n-- PostgreSQL database dump\n--\n\nSET transaction_timeout = 0;\n\n-- Name: users; Type: TABLE;\n"
PAYLOAD = b"COPY public.users FROM stdin;\nSET transaction_timeout = 0;\n\\.\n"


def fixture(*, permission=True, collision=False, wrong_identity=False, tamper_marker=False):
    state = {"created": False, "marker": None}

    async def control_value(sql, *args):
        if "rolcreatedb" in sql:
            return permission
        return 123 if state["created"] or collision else None

    async def execute(sql):
        if sql.startswith("CREATE DATABASE"):
            state["created"] = True
        if sql.startswith("COMMENT ON DATABASE"):
            state["marker"] = sql.split(" IS '", 1)[1][:-1]
        if sql.startswith("DROP DATABASE"):
            state["created"] = False

    async def identity(*args):
        return {"oid": 123, "marker": "changed" if tamper_marker else state["marker"]}

    source = SimpleNamespace(
        fetch=AsyncMock(return_value=[{"version_num": M["BASE"]}]),
        fetchval=AsyncMock(return_value="160004"),
        close=AsyncMock(),
    )
    control = SimpleNamespace(
        fetchval=AsyncMock(side_effect=control_value),
        fetchrow=AsyncMock(side_effect=identity),
        execute=AsyncMock(side_effect=execute),
        close=AsyncMock(),
    )

    async def target_fetch(sql):
        if "alembic_version" in sql:
            return [{"version_num": M["BASE"]}]
        return [{"tablename": t} for t in M["REQUIRED_TABLES"]]

    target = SimpleNamespace(
        fetchval=AsyncMock(return_value="source" if wrong_identity else NAME),
        fetch=AsyncMock(side_effect=target_fetch),
        close=AsyncMock(),
    )
    return AsyncMock(side_effect=[source, control, target]), source, control, target


def process(*, fail=None):
    def run(args, **kwargs):
        if "--no-owner" in args:
            if "--file=-" not in args:
                return SimpleNamespace(returncode=1)
            kwargs["stdout"].write(HEADER + PAYLOAD)
            return SimpleNamespace(returncode=1 if fail == "render" else 0)
        return SimpleNamespace(returncode=1 if fail == "restore" else 0)

    return MagicMock(side_effect=run)


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / "backup.dump"
        self.archive.write_bytes(b"PGDMP synthetic archive")
        self.fingerprint = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    async def exercise(self, *, connect=None, run=None, name=NAME, fingerprint=None):
        return await M["rehearse_restore"](
            DSN,
            self.archive,
            fingerprint or self.fingerprint,
            "restore",
            "psql",
            ENV,
            connect=connect or fixture()[0],
            run=run or process(),
            name=name,
        )

    async def test_success_restores_checks_and_removes_marked_copy(self):
        connect, source, control, target = fixture()
        run = process()
        result = await self.exercise(connect=connect, run=run)
        self.assertEqual(result["restore_status"], "restored_verified_and_removed")
        self.assertTrue(result["restore_tested"])
        self.assertTrue(result["temporary_database_removed"])
        self.assertTrue(result["archive_unchanged"])
        self.assertFalse(result["application_database_migrations_applied"])
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(run.call_args_list[1].kwargs["env"]["PGDATABASE"], NAME)
        self.assertNotIn("PGDATABASE", run.call_args_list[0].kwargs["env"])
        self.assertIn("--file=-", run.call_args_list[0].args[0])
        self.assertNotIn("private_password", str(result))
        for connection in (source, control, target):
            connection.close.assert_awaited_once()

    async def test_compatibility_adjustment_changes_only_one_header_prefix(self):
        path = self.archive.with_suffix(".sql")
        for header in (HEADER, HEADER.replace(b"\n", b"\r\n")):
            path.write_bytes(header + PAYLOAD)
            self.assertTrue(M["normalize_restore_header"](path, 16))
            self.assertEqual(path.read_bytes(), header.replace(b"SET ", b"--  ", 1) + PAYLOAD)

    async def test_newer_server_script_is_unchanged(self):
        self.assertFalse(M["normalize_restore_header"](self.archive, 18))
        self.assertEqual(self.archive.read_bytes(), b"PGDMP synthetic archive")

    async def test_unrecognized_header_or_duplicate_setting_rejected(self):
        for data in (
            b"not a script",
            HEADER.replace(b"SET transaction_timeout = 0;", b"other"),
            HEADER.replace(
                b"SET transaction_timeout = 0;",
                b"SET transaction_timeout = 0;\nSET transaction_timeout = 0;",
            ),
        ):
            self.archive.write_bytes(data)
            with self.assertRaises(ValueError):
                M["normalize_restore_header"](self.archive, 16)

    async def test_archive_hash_mismatch_does_not_connect(self):
        connect = AsyncMock()
        result = await self.exercise(connect=connect, fingerprint="0" * 64)
        self.assertEqual(result["restore_status"], "archive_hash_mismatch")
        connect.assert_not_awaited()

    async def test_invalid_temporary_names_are_rejected(self):
        for name in ("source", "public", "step543_bad; DROP DATABASE source"):
            with self.assertRaises(ValueError):
                await self.exercise(name=name)

    async def test_missing_createdb_permission_does_not_write(self):
        connect, _source, control, _target = fixture(permission=False)
        result = await self.exercise(connect=connect)
        self.assertEqual(result["restore_status"], "database_creation_permission_missing")
        control.execute.assert_not_awaited()

    async def test_name_collision_never_dropped(self):
        connect, _source, control, _target = fixture(collision=True)
        result = await self.exercise(connect=connect)
        self.assertEqual(result["restore_status"], "temporary_name_collision")
        control.execute.assert_not_awaited()

    async def test_source_version_change_stops_creation(self):
        connect, source, control, _target = fixture()
        source.fetch.return_value = [{"version_num": "private unexpected revision"}]
        result = await self.exercise(connect=connect)
        self.assertEqual(result["restore_status"], "source_head_changed")
        self.assertNotIn("private unexpected revision", str(result))
        control.execute.assert_not_awaited()

    async def test_restore_failure_still_removes_temporary_database(self):
        result = await self.exercise(run=process(fail="restore"))
        self.assertEqual(result["restore_status"], "restore_failed")
        self.assertTrue(result["temporary_database_removed"])
        self.assertFalse(result["restore_tested"])

    async def test_marker_mismatch_refuses_drop(self):
        connect, _source, control, _target = fixture(tamper_marker=True)
        result = await self.exercise(connect=connect)
        self.assertEqual(result["restore_status"], "temporary_cleanup_failed")
        self.assertFalse(any(c.args[0].startswith("DROP") for c in control.execute.await_args_list))

    async def test_wrong_target_identity_blocks_verification(self):
        connect, _source, _control, _target = fixture(wrong_identity=True)
        run = process()
        result = await self.exercise(connect=connect, run=run)
        self.assertFalse(result["restore_tested"])
        self.assertEqual(result["failure_stage"], "target_identity")
        run.assert_not_called()

    async def test_render_failure_never_runs_psql(self):
        run = process(fail="render")
        result = await self.exercise(run=run)
        self.assertEqual(run.call_count, 1)
        self.assertFalse(result["restore_tested"])
        self.assertTrue(result["temporary_database_removed"])

    async def test_sql_commands_only_create_mark_and_drop_known_temporary_name(self):
        connect, _source, control, _target = fixture()
        await self.exercise(connect=connect)
        for call in control.execute.await_args_list:
            self.assertIn('"' + NAME + '"', call.args[0])
            self.assertTrue(
                call.args[0].startswith(
                    ("CREATE DATABASE", "COMMENT ON DATABASE", "REVOKE", "DROP DATABASE")
                )
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
