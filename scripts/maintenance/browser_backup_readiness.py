"""Check backup tools and catalog privileges without exporting application data."""

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path

BASE = "0006_job_recovery_operations"
PRIVILEGES_SQL = """
SELECT
  NOT EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
      AND CASE WHEN c.relkind IN ('r','p','m')
          THEN NOT has_table_privilege(c.oid, 'SELECT') ELSE false END
  ) AS tables_readable,
  NOT EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
      AND CASE WHEN c.relkind='S'
          THEN NOT has_sequence_privilege(c.oid, 'SELECT') ELSE false END
  ) AS sequences_readable,
  (SELECT r.rolsuper OR r.rolbypassrls OR NOT EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
      AND c.relrowsecurity
  ) FROM pg_roles r WHERE r.rolname=current_user) AS row_security_compatible
"""


def candidates():
    pairs = []
    dump = shutil.which("pg_dump")
    if dump:
        path = Path(dump)
        pairs.append((path, path.with_name("pg_restore" + path.suffix)))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    folder = program_files / "PostgreSQL"
    if folder.is_dir():
        versions = [p for p in folder.iterdir() if p.is_dir() and re.fullmatch(r"\d{1,2}", p.name)]
        for version in sorted(versions, key=lambda p: int(p.name), reverse=True)[:4]:
            pairs.append((version / "bin/pg_dump.exe", version / "bin/pg_restore.exe"))
    return list(dict.fromkeys(pairs))


def probe_tools(pairs=None, *, run=subprocess.run):
    found = []
    for dump, restore in candidates() if pairs is None else pairs:
        if not dump.is_file() or not restore.is_file():
            continue
        majors = []
        for path, name in ((dump, "pg_dump"), (restore, "pg_restore")):
            try:
                result = run(
                    [str(path), "--version"], capture_output=True, text=True, timeout=5, check=False
                )
                match = re.fullmatch(
                    rf"{name} \(PostgreSQL\) (\d{{1,2}})(?:\.\d+){{0,2}}(?: \([^\r\n]*\))?\s*",
                    result.stdout,
                )
                majors.append(int(match.group(1)) if result.returncode == 0 and match else None)
            except Exception:
                majors.append(None)
        if majors[0] is not None and majors[0] == majors[1] and majors[0] >= 10:
            found.append({"dump_major": majors[0], "restore_major": majors[1]})
    return sorted(found, key=lambda item: item["dump_major"], reverse=True)


async def inspect_backup_readiness(dsn, *, connect=None, tools=None):
    tools = probe_tools() if tools is None else tools
    result = {
        "backup_readiness_status": "not_configured",
        "connection_attempted": False,
        "connection_established": False,
        "read_only_transaction_confirmed": False,
        "rollback_confirmed": False,
        "checks": {},
        "client_tools_found": bool(tools),
        "backup_created": False,
        "restore_tested": False,
        "upgrade_authorized": False,
        "application_account_records_read": False,
        "migrations_applied": False,
    }
    if not dsn:
        return result
    if connect is None:
        import asyncpg

        connect = asyncpg.connect
    connection = transaction = None
    stage = "connect"
    try:
        result["connection_attempted"] = True
        connection = await connect(
            dsn=dsn,
            timeout=5,
            command_timeout=5,
            server_settings={
                "default_transaction_read_only": "on",
                "application_name": "browser_backup_readiness",
            },
        )
        result["connection_established"] = True
        stage = "transaction"
        transaction = connection.transaction(isolation="repeatable_read", readonly=True)
        await transaction.start()
        if await connection.fetchval("SHOW transaction_read_only") != "on":
            result["backup_readiness_status"] = "read_only_guard_failed"
            return result
        result["read_only_transaction_confirmed"] = True
        await connection.execute("SET LOCAL statement_timeout = '5s'")
        await connection.execute("SET LOCAL lock_timeout = '2s'")
        stage = "migration_head"
        heads = [
            row["version_num"]
            for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
        ]
        if heads != [BASE]:
            result["backup_readiness_status"] = "database_head_changed"
            return result
        stage = "catalog_checks"
        version = await connection.fetchval("SHOW server_version_num")
        if not isinstance(version, str) or re.fullmatch(r"[1-9]\d{5}", version) is None:
            raise ValueError("invalid server version metadata")
        major = int(version) // 10000
        supported = [
            tool
            for tool in tools
            if tool["dump_major"] >= major and tool["restore_major"] == tool["dump_major"]
        ]
        result["server_major"] = major
        if supported:
            result["selected_client_major"] = supported[0]["dump_major"]
        row = await connection.fetchrow(PRIVILEGES_SQL)
        result["checks"] = {
            key: row[key] is True
            for key in (
                "tables_readable",
                "sequences_readable",
                "row_security_compatible",
            )
        }
        result["checks"]["compatible_backup_clients"] = bool(supported)
        result["backup_readiness_status"] = (
            "backup_prerequisites_passed" if all(result["checks"].values()) else "blocked"
        )
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        result.update(
            backup_readiness_status="unavailable",
            failure_stage=stage,
            failure_code=code
            if code
            in {"42809", "42501", "57014", "42P01", "42703", "25006", "08001", "08006", "53300"}
            else "unclassified",
        )
    finally:
        if transaction is not None:
            try:
                await asyncio.wait_for(transaction.rollback(), timeout=3)
                result["rollback_confirmed"] = True
            except Exception:
                result["backup_readiness_status"] = "rollback_not_confirmed"
        if connection is not None:
            try:
                await connection.close(timeout=2)
            except Exception:
                result["backup_readiness_status"] = "connection_cleanup_not_confirmed"
    return result
