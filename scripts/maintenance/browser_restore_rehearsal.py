"""Restore a verified archive only into a newly created, marked temporary database."""

import asyncio
import hashlib
import os
import re
import secrets
import subprocess

from sqlalchemy.engine import make_url

BASE = "0006_job_recovery_operations"
REQUIRED_TABLES = {"users", "organizations", "alembic_version"}


def normalize_restore_header(path, server_major):
    """PG18 emits this PG17+ setting even when restoring a PG16 archive."""
    if server_major >= 17:
        return False
    with path.open("r+b") as stream:
        header = stream.read(65536)
        boundary = header.find(b"-- Name:")
        if (
            not header.startswith(
                (b"--\n-- PostgreSQL database dump\n--", b"--\r\n-- PostgreSQL database dump\r\n--")
            )
            or boundary < 0
        ):
            raise ValueError("restore header not recognized")
        prefix = header[:boundary]
        matches = list(re.finditer(rb"(?m)^SET transaction_timeout = 0;\r?$", prefix))
        if prefix.count(b"SET transaction_timeout = 0;") != 1 or len(matches) != 1:
            raise ValueError("restore compatibility guard failed")
        offset = matches[0].start()
        stream.seek(offset)
        stream.write(b"--  ")  # Same length as SET-space; no data bytes move.
        stream.flush()
        os.fsync(stream.fileno())
    return True


def render_and_restore(archive, script, restore, psql, env, server_major, *, run=subprocess.run):
    result = {
        "restore_command_completed": False,
        "copy_account_data_restored": False,
        "compatibility_header_adjusted": False,
    }
    stage = "render_sql"
    try:
        offline = {key: value for key, value in env.items() if not key.upper().startswith("PG")}
        with script.open("xb") as stream:
            rendered = run(
                [
                    str(restore),
                    "--file=-",
                    "--no-owner",
                    "--no-privileges",
                    "--no-tablespaces",
                    str(archive),
                ],
                env=offline,
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            stream.flush()
            os.fsync(stream.fileno())
        if rendered.returncode != 0:
            raise RuntimeError("archive rendering failed")
        stage = "compatibility_header"
        result["compatibility_header_adjusted"] = normalize_restore_header(script, server_major)
        stage = "restore_copy"
        result["copy_account_data_restored"] = True  # An attempt can restore partial data.
        restored = run(
            [
                str(psql),
                "--no-password",
                "--no-psqlrc",
                "--set=ON_ERROR_STOP=1",
                "--single-transaction",
                "--file=" + str(script),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
        if restored.returncode != 0:
            raise RuntimeError("restore failed")
        result["restore_command_completed"] = True
    except Exception:
        result["failure_stage"] = stage
    return result


async def rehearse_restore(
    dsn,
    archive,
    fingerprint,
    restore,
    psql,
    environment_factory,
    *,
    connect=None,
    run=subprocess.run,
    name=None,
):
    name = name or "step543_" + secrets.token_hex(12)
    result = {
        "restore_status": "not_started",
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
    if re.fullmatch(r"step543_[0-9a-f]{24}", name) is None:
        raise ValueError("invalid rehearsal database name")
    source_url = make_url(dsn)
    if source_url.database == name:
        raise ValueError("source database cannot be a restore target")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != fingerprint:
            result["restore_status"] = "archive_hash_mismatch"
            return result
    if connect is None:
        import asyncpg

        connect = asyncpg.connect
    source = control = target = None
    created_oid = None
    marker = "step543:" + secrets.token_hex(16)
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
            result["restore_status"] = "source_head_changed"
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
            result["restore_status"] = "database_creation_permission_missing"
            return result
        stage = "create_temporary_database"
        if await control.fetchval("SELECT oid FROM pg_database WHERE datname=$1", name) is not None:
            result["restore_status"] = "temporary_name_collision"
            return result
        await control.execute(f'CREATE DATABASE "{name}" TEMPLATE template0')
        result["temporary_database_created"] = True
        created_oid = await control.fetchval("SELECT oid FROM pg_database WHERE datname=$1", name)
        await control.execute(f"COMMENT ON DATABASE \"{name}\" IS '{marker}'")
        await control.execute(f'REVOKE CONNECT, TEMPORARY ON DATABASE "{name}" FROM PUBLIC')
        target_dsn = source_url.set(database=name).render_as_string(hide_password=False)
        env = environment_factory(target_dsn)
        env["PGOPTIONS"] = "-c default_transaction_read_only=off -c lock_timeout=2000"
        env["PGAPPNAME"] = "step543_restore_rehearsal"
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
            result["restore_status"] = "restore_failed"
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
        result["restore_status"] = (
            "copy_verified_cleanup_pending"
            if result["restore_tested"]
            else "copy_verification_failed"
        )
    except Exception:
        result.update(restore_status="unavailable_or_failed", failure_stage=stage)
    finally:
        if target is not None:
            try:
                await target.close(timeout=3)
            except Exception:
                result["restore_status"] = "copy_connection_cleanup_failed"
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
                    result["restore_status"] = "temporary_cleanup_failed"
            try:
                await control.close(timeout=3)
            except Exception:
                result["restore_status"] = "maintenance_cleanup_failed"
        if source is not None:
            try:
                heads = await source.fetch("SELECT version_num FROM public.alembic_version")
                result["source_head_unchanged"] = [row["version_num"] for row in heads] == [BASE]
            except Exception:
                result["restore_status"] = "source_head_unverified"
            try:
                await source.close(timeout=3)
            except Exception:
                result["restore_status"] = "source_cleanup_failed"
        try:
            with archive.open("rb") as stream:
                result["archive_unchanged"] = (
                    hashlib.file_digest(stream, "sha256").hexdigest() == fingerprint
                )
        except Exception:
            result["restore_status"] = "archive_recheck_failed"
        if result["restore_status"] == "copy_verified_cleanup_pending":
            result["restore_status"] = (
                "restored_verified_and_removed"
                if result["temporary_database_removed"]
                and result["source_head_unchanged"]
                and result["archive_unchanged"]
                else "cleanup_or_input_unverified"
            )
    return result
