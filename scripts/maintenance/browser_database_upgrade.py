"""Apply reviewed additive migrations atomically after a fresh validated backup."""

import asyncio
import re
import runpy
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url

BASE = "0006_job_recovery_operations"
HEAD = "0010_account_auth_storage"
TABLES_SQL = """
SELECT n.nspname AS schema_name, c.relname AS table_name
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r','p') ORDER BY n.nspname,c.relname
"""


def quote_identifier(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("invalid catalog identifier")
    return '"' + value.replace('"', '""') + '"'


def lock_targets(rows):
    if not rows or len(rows) > 1000:
        raise ValueError("unexpected application table inventory")
    found = {(row["schema_name"], row["table_name"]) for row in rows}
    if not {("public", name) for name in ("users", "organizations", "alembic_version")}.issubset(
        found
    ):
        raise ValueError("application baseline tables missing")
    if any(schema.startswith("pg_") or schema == "information_schema" for schema, _ in found):
        raise ValueError("system table lock rejected")
    return ", ".join(
        quote_identifier(schema) + "." + quote_identifier(table) for schema, table in sorted(found)
    )


async def metadata(connection, inspector):
    heads = [
        row["version_num"]
        for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
    ]
    columns = await connection.fetch(
        inspector["COLUMNS_SQL"], "public", list(inspector["REQUIRED_COLUMNS"])
    )
    constraints = await connection.fetch(
        inspector["CONSTRAINTS_SQL"],
        "public",
        [*inspector["KEY_CONSTRAINTS"], *inspector["CHECK_CONSTRAINTS"]],
    )
    return inspector["assess_metadata"](columns, constraints, heads)


async def apply_upgrade(
    dsn,
    sql,
    archive,
    dump,
    restore,
    client_major,
    inspector,
    backup_tools,
    *,
    connect=None,
    run=subprocess.run,
):
    result = {
        "upgrade_status": "not_configured",
        "connection_attempted": False,
        "connection_established": False,
        "application_migrations_applied_by_this_run": False,
        "commit_outcome": "not_attempted",
        "rollback_confirmed": False,
        "checks": {},
        "live_activation_ready": False,
    }
    if not dsn:
        return result
    reviewed = runpy.run_path(str(Path(__file__).with_name("browser_upgrade_rehearsal.py")))
    planner = runpy.run_path(str(Path(__file__).with_name("browser_upgrade_plan.py")))
    if planner["assess_range_sql"](sql)["offline_plan_checks_passed"] is not True:
        raise ValueError("unreviewed migration range")
    body = reviewed["transaction_body"](sql)
    connection = transaction = None
    stage = "connect"
    try:
        url = make_url(dsn)
        if not url.database or re.fullmatch(r"step\d+_[0-9a-f]{24}", url.database):
            raise ValueError("temporary upgrade destination rejected")
        if connect is None:
            import asyncpg

            connect = asyncpg.connect
        result["connection_attempted"] = True
        connection = await connect(
            dsn=dsn,
            timeout=5,
            command_timeout=30,
            server_settings={
                "default_transaction_read_only": "on",
                "application_name": "step545_account_upgrade",
            },
        )
        result["connection_established"] = True
        if await connection.fetchval("SELECT current_database()") != url.database:
            raise ValueError("configured database identity mismatch")
        stage = "transaction"
        transaction = connection.transaction(isolation="read_committed", readonly=False)
        await transaction.start()
        await connection.execute("SET TRANSACTION READ WRITE")
        if await connection.fetchval("SHOW transaction_read_only") != "off":
            raise ValueError("read-write guard failed")
        await connection.execute("SET LOCAL lock_timeout = '2s'")
        await connection.execute("SET LOCAL statement_timeout = '20s'")
        await connection.execute("SET LOCAL idle_in_transaction_session_timeout = '300s'")
        await connection.execute("SET LOCAL search_path TO public, pg_catalog")
        if not await connection.fetchval("SELECT pg_try_advisory_xact_lock(545, 10)"):
            result["upgrade_status"] = "another_upgrade_in_progress"
            return result
        heads = [
            row["version_num"]
            for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
        ]
        if heads == [HEAD]:
            result["metadata"] = await metadata(connection, inspector)
            result["upgrade_status"] = (
                "already_current"
                if result["metadata"]["catalog_metadata_compatible"]
                else "current_head_schema_mismatch"
            )
            return result
        if heads != [BASE]:
            result["upgrade_status"] = "database_head_changed"
            return result
        stage = "freeze_application_writes"
        targets = lock_targets(await connection.fetch(TABLES_SQL))
        await connection.execute("LOCK TABLE " + targets + " IN SHARE MODE NOWAIT")
        # READ COMMITTED exports a new snapshot after the write-blocking locks.
        # pg_dump can take ACCESS SHARE locks while these SHARE locks are held.
        if [
            row["version_num"]
            for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
        ] != [BASE]:
            raise ValueError("migration head changed while acquiring locks")
        stage = "fresh_backup"
        version = await connection.fetchval("SHOW server_version_num")
        if (
            not isinstance(version, str)
            or re.fullmatch(r"[1-9]\d{5}", version) is None
            or client_major < int(version) // 10000
        ):
            raise ValueError("backup client compatibility changed")
        snapshot = await connection.fetchval("SELECT pg_export_snapshot()")
        env = backup_tools["backup_environment"](dsn)
        result["fresh_backup"] = await asyncio.to_thread(
            backup_tools["write_archive"], archive, dump, restore, env, snapshot, run=run
        )
        result["fresh_backup"]["archive_path"] = str(archive)
        if result["fresh_backup"]["archive_validated"] is not True:
            result["upgrade_status"] = "fresh_backup_failed"
            return result
        stage = "lock_schema_for_upgrade"
        await connection.execute("LOCK TABLE " + targets + " IN ACCESS EXCLUSIVE MODE NOWAIT")
        stage = "execute_migrations"
        await connection.execute(body)
        stage = "verify_schema"
        result["metadata"] = await metadata(connection, inspector)
        result["checks"]["catalog_metadata_compatible"] = (
            result["metadata"]["catalog_metadata_compatible"] is True
        )
        if not all(result["checks"].values()):
            result["upgrade_status"] = "schema_verification_failed"
            return result
        stage = "commit"
        result["commit_outcome"] = "unknown"
        result["application_migrations_applied_by_this_run"] = None
        await transaction.commit()
        result.update(
            upgrade_status="applied_and_verified",
            commit_outcome="confirmed",
            application_migrations_applied_by_this_run=True,
        )
        stage = "post_commit_verification"
        result["post_commit_metadata"] = await metadata(connection, inspector)
        if result["post_commit_metadata"]["catalog_metadata_compatible"] is not True:
            result["upgrade_status"] = "applied_post_commit_verification_failed"
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        result.update(
            upgrade_status="failed",
            failure_stage=stage,
            failure_code=code
            if code
            in {"42501", "25006", "57014", "55P03", "23503", "23505", "23514", "42P07", "42701"}
            else "unclassified",
        )
    finally:
        if transaction is not None and result["commit_outcome"] != "confirmed":
            try:
                await transaction.rollback()
                result["rollback_confirmed"] = True
            except Exception:
                result["upgrade_status"] = "rollback_not_confirmed"
        if connection is not None:
            try:
                await connection.close(timeout=3)
            except Exception:
                result["upgrade_status"] = "connection_cleanup_failed"
    return result
