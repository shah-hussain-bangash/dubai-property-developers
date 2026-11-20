"""Rehearse the reviewed account upgrade only on a restored, disposable database."""

import asyncio
import hashlib
import re
import runpy
import secrets
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url

_restore = runpy.run_path(str(Path(__file__).with_name("browser_restore_rehearsal.py")))
render_and_restore = _restore["render_and_restore"]
BASE = _restore["BASE"]
REQUIRED_TABLES = _restore["REQUIRED_TABLES"]
HEAD = "0010_account_auth_storage"


def transaction_body(sql):
    clean = re.sub(r"(?m)^\s*--[^\n]*", "", sql)
    parts = [part.strip() for part in clean.split(";") if part.strip()]
    if not parts or parts[0].upper() != "BEGIN" or parts[-1].upper() != "COMMIT":
        raise ValueError("reviewed transaction envelope required")
    parts = parts[1:-1]
    if not parts or any(
        not part.lower().startswith(
            ("create table ", "create index ", "alter table ", "update public.alembic_version ")
        )
        for part in parts
    ):
        raise ValueError("unsupported upgrade SQL")
    return ";\n".join(parts) + ";\n"


async def verify_upgrade(connection, name, sql, inspector):
    result = {
        "upgrade_status": "not_started",
        "checks": {},
        "committed_on_copy": False,
        "application_database_migrations_applied": False,
    }
    if re.fullmatch(r"step544_[0-9a-f]{24}", name) is None:
        raise ValueError("invalid upgrade copy name")
    body = transaction_body(sql)
    transaction = None
    stage = "copy_identity"
    try:
        if await connection.fetchval("SELECT current_database()") != name:
            raise ValueError("copy identity guard failed")
        transaction = connection.transaction(isolation="repeatable_read", readonly=False)
        await transaction.start()
        await connection.execute("SET TRANSACTION READ WRITE")
        if await connection.fetchval("SHOW transaction_read_only") != "off":
            raise ValueError("copy read-write guard failed")
        await connection.execute("SET LOCAL lock_timeout = '2s'")
        await connection.execute("SET LOCAL statement_timeout = '20s'")
        await connection.execute("SET LOCAL search_path TO public, pg_catalog")
        heads = await connection.fetch("SELECT version_num FROM public.alembic_version")
        if [row["version_num"] for row in heads] != [BASE]:
            raise ValueError("copy migration head changed")
        stage = "execute_upgrade"
        await connection.execute(body)
        stage = "verify_upgrade"
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
        metadata = inspector["assess_metadata"](columns, constraints, heads)
        result["metadata"] = metadata
        result["checks"] = {
            "copy_head_is_0010": heads == [HEAD],
            "catalog_metadata_compatible": metadata["catalog_metadata_compatible"] is True,
            "legacy_approval_fields_preserved": await connection.fetchval(
                "SELECT NOT EXISTS (SELECT 1 FROM public.users WHERE approval_status IS NOT NULL OR approval_decided_by IS NOT NULL OR approval_decided_at IS NOT NULL)"
            )
            is True,
            "no_identities_created": await connection.fetchval(
                "SELECT NOT EXISTS (SELECT 1 FROM public.user_external_identities)"
            )
            is True,
            "no_sessions_created": await connection.fetchval(
                "SELECT NOT EXISTS (SELECT 1 FROM public.account_sessions)"
            )
            is True,
        }
        if not all(result["checks"].values()):
            result["upgrade_status"] = "verification_failed"
            return result
        await transaction.commit()
        result.update(upgrade_status="passed", committed_on_copy=True)
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        result.update(
            upgrade_status="failed",
            failure_stage=stage,
            failure_code=code
            if code in {"42501", "25006", "57014", "23503", "23505", "23514", "42P07", "42701"}
            else "unclassified",
        )
    finally:
        if transaction is not None and not result["committed_on_copy"]:
            try:
                await transaction.rollback()
            except Exception:
                result["upgrade_status"] = "rollback_not_confirmed"
    return result


async def rehearse_upgrade(
    dsn,
    archive,
    fingerprint,
    restore,
    psql,
    environment_factory,
    sql,
    inspector,
    *,
    connect=None,
    run=subprocess.run,
    name=None,
):
    assessment = runpy.run_path(str(Path(__file__).with_name("browser_upgrade_plan.py")))[
        "assess_range_sql"
    ](sql)
    if assessment["offline_plan_checks_passed"] is not True:
        raise ValueError("unreviewed upgrade SQL")
    name = name or "step544_" + secrets.token_hex(12)
    result = {
        "upgrade_rehearsal_status": "not_started",
        "temporary_database": name,
        "connection_attempted": False,
        "connection_established": False,
        "temporary_database_created": False,
        "temporary_database_removed": False,
        "restore_command_completed": False,
        "restore_tested": False,
        "checks": {},
        "application_database_migrations_applied": False,
        "source_application_account_records_read": False,
        "archive_unchanged": False,
        "source_head_unchanged": False,
        "live_activation_ready": False,
    }
    if re.fullmatch(r"step544_[0-9a-f]{24}", name) is None:
        raise ValueError("invalid rehearsal database name")
    source_url = make_url(dsn)
    if source_url.database == name:
        raise ValueError("source database cannot be a restore target")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != fingerprint:
            result["upgrade_rehearsal_status"] = "archive_hash_mismatch"
            return result
    if connect is None:
        import asyncpg

        connect = asyncpg.connect
    source = control = target = None
    created_oid = None
    marker = "step544:" + secrets.token_hex(16)
    stage = "source_preflight"
    try:
        result["connection_attempted"] = True
        source = await connect(
            dsn=dsn,
            timeout=5,
            command_timeout=5,
            server_settings={"default_transaction_read_only": "on"},
        )
        result["connection_established"] = True
        heads = await source.fetch("SELECT version_num FROM public.alembic_version")
        if [row["version_num"] for row in heads] != [BASE]:
            result["upgrade_rehearsal_status"] = "source_head_changed"
            return result
        version = await source.fetchval("SHOW server_version_num")
        if not isinstance(version, str) or re.fullmatch(r"[1-9]\d{5}", version) is None:
            raise ValueError("invalid server metadata")
        major = int(version) // 10000
        stage = "maintenance_connection"
        control_dsn = source_url.set(database="postgres").render_as_string(hide_password=False)
        control = await connect(
            dsn=control_dsn,
            timeout=5,
            command_timeout=10,
            server_settings={"default_transaction_read_only": "off"},
        )
        if not await control.fetchval(
            "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user"
        ):
            result["upgrade_rehearsal_status"] = "database_creation_permission_missing"
            return result
        stage = "create_temporary_database"
        if await control.fetchval("SELECT oid FROM pg_database WHERE datname=$1", name) is not None:
            result["upgrade_rehearsal_status"] = "temporary_name_collision"
            return result
        await control.execute(f'CREATE DATABASE "{name}" TEMPLATE template0')
        result["temporary_database_created"] = True
        created_oid = await control.fetchval("SELECT oid FROM pg_database WHERE datname=$1", name)
        await control.execute(f"COMMENT ON DATABASE \"{name}\" IS '{marker}'")
        await control.execute(f'REVOKE CONNECT, TEMPORARY ON DATABASE "{name}" FROM PUBLIC')
        target_dsn = source_url.set(database=name).render_as_string(hide_password=False)
        env = environment_factory(target_dsn)
        env["PGOPTIONS"] = "-c default_transaction_read_only=off -c lock_timeout=2000"
        env["PGAPPNAME"] = "step544_restore_rehearsal"
        if env["PGDATABASE"] != name:
            raise ValueError("restore destination mismatch")
        stage = "target_identity"
        target = await connect(
            dsn=target_dsn,
            timeout=5,
            command_timeout=5,
            server_settings={"default_transaction_read_only": "on"},
        )
        actual = await target.fetchval("SELECT current_database()")
        if actual != name:
            raise ValueError("copy identity guard failed")
        stage = "restore_archive"
        script = archive.with_name(name + "_restore.sql")
        result.update(
            await asyncio.to_thread(
                render_and_restore, archive, script, restore, psql, env, major, run=run
            )
        )
        if not result["restore_command_completed"]:
            result["upgrade_rehearsal_status"] = "restore_failed"
            return result
        stage = "verify_copy"
        actual = await target.fetchval("SELECT current_database()")
        if actual != name:
            raise ValueError("copy identity guard failed")
        restored_heads = await target.fetch("SELECT version_num FROM public.alembic_version")
        tables = await target.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        result["checks"] = {
            "restore_process_succeeded": True,
            "temporary_database_identity": actual == name,
            "restored_migration_head": [row["version_num"] for row in restored_heads] == [BASE],
            "required_tables_restored": REQUIRED_TABLES.issubset(
                {row["tablename"] for row in tables}
            ),
        }
        result["restore_tested"] = all(result["checks"].values())
        if result["restore_tested"]:
            stage = "copy_upgrade"
            result["copy_upgrade"] = await verify_upgrade(target, name, sql, inspector)
            if result["copy_upgrade"]["upgrade_status"] != "passed":
                result["upgrade_rehearsal_status"] = "copy_upgrade_failed"
                return result

        result["upgrade_rehearsal_status"] = (
            "copy_verified_cleanup_pending"
            if result["restore_tested"]
            else "copy_verification_failed"
        )
    except Exception:
        result.update(upgrade_rehearsal_status="unavailable_or_failed", failure_stage=stage)
    finally:
        if target is not None:
            try:
                await target.close(timeout=3)
            except Exception:
                result["upgrade_rehearsal_status"] = "copy_connection_cleanup_failed"
        if control is not None:
            if result["temporary_database_created"]:
                try:
                    identity = await control.fetchrow(
                        "SELECT oid, shobj_description(oid,'pg_database') AS marker FROM pg_database WHERE datname=$1",
                        name,
                    )
                    if (
                        identity is None
                        or identity["oid"] != created_oid
                        or identity["marker"] != marker
                    ):
                        raise ValueError("temporary cleanup identity guard failed")
                    await control.execute(f'DROP DATABASE "{name}"')
                    result["temporary_database_removed"] = (
                        await control.fetchval("SELECT oid FROM pg_database WHERE datname=$1", name)
                        is None
                    )
                except Exception:
                    result["upgrade_rehearsal_status"] = "temporary_cleanup_failed"
            try:
                await control.close(timeout=3)
            except Exception:
                result["upgrade_rehearsal_status"] = "maintenance_cleanup_failed"
        if source is not None:
            try:
                heads = await source.fetch("SELECT version_num FROM public.alembic_version")
                result["source_head_unchanged"] = [row["version_num"] for row in heads] == [BASE]
            except Exception:
                result["upgrade_rehearsal_status"] = "source_head_unverified"
            try:
                await source.close(timeout=3)
            except Exception:
                result["upgrade_rehearsal_status"] = "source_cleanup_failed"
        try:
            with archive.open("rb") as stream:
                result["archive_unchanged"] = (
                    hashlib.file_digest(stream, "sha256").hexdigest() == fingerprint
                )
        except Exception:
            result["upgrade_rehearsal_status"] = "archive_recheck_failed"
        if result["upgrade_rehearsal_status"] == "copy_verified_cleanup_pending":
            result["upgrade_rehearsal_status"] = (
                "upgraded_verified_and_removed"
                if result["temporary_database_removed"]
                and result["source_head_unchanged"]
                and result["archive_unchanged"]
                else "cleanup_or_input_unverified"
            )
    return result
