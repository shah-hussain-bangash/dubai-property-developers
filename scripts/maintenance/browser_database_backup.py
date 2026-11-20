"""Create a local custom-format backup from an exported read-only snapshot."""

import asyncio
import hashlib
import os
import re
import subprocess

from sqlalchemy.engine import make_url

BASE = "0006_job_recovery_operations"


def backup_environment(dsn):
    url = make_url(dsn)
    if (
        url.drivername != "postgresql"
        or not url.host
        or not url.database
        or url.query.keys() - {"sslmode"}
    ):
        raise ValueError("unsupported backup connection")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("PG") and key != "DATABASE_URL"
    }
    env.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGDATABASE=url.database,
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
        PGSSLMODE=url.query.get("sslmode", "prefer"),
        PGCONNECT_TIMEOUT="5",
        PGAPPNAME="step542_database_backup",
        PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=60000 -c lock_timeout=2000",
    )
    return env


def write_archive(path, dump, restore, env, snapshot, *, run=subprocess.run):
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{8}-[1-9][0-9]*", snapshot) is None:
        raise ValueError("invalid exported snapshot")
    result = {
        "backup_created": False,
        "archive_validated": False,
        "pg_dump_connection_attempted": False,
        "application_account_records_read": False,
    }
    stage = "archive_create"
    try:
        # Exclusive creation preserves previous/partial archives on every failure.
        with path.open("xb") as stream:
            stage = "pg_dump"
            result["pg_dump_connection_attempted"] = True
            result["application_account_records_read"] = True
            dumped = run(
                [
                    str(dump),
                    "--format=custom",
                    "--no-password",
                    "--lock-wait-timeout=5000",
                    "--snapshot=" + snapshot,
                ],
                env=env,
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            stream.flush()
            os.fsync(stream.fileno())
        if dumped.returncode != 0:
            raise RuntimeError("backup command failed")
        result["backup_created"] = True
        stage = "archive_header"
        with path.open("rb") as stream:
            if stream.read(5) != b"PGDMP":
                raise RuntimeError("invalid archive header")
        stage = "archive_inventory"
        # pg_restore is never passed a database: both operations are offline.
        offline_env = {key: value for key, value in env.items() if not key.upper().startswith("PG")}
        listed = run(
            [str(restore), "--list", str(path)],
            env=offline_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if listed.returncode != 0 or not all(
            re.search(rf"(?m)^\d+;\s+\d+\s+\d+ TABLE DATA public {table} ", listed.stdout)
            for table in ("users", "organizations", "alembic_version")
        ):
            raise RuntimeError("required archive entries missing")
        stage = "archive_decode"
        decoded = run(
            [str(restore), "--file=" + os.devnull, str(path)],
            env=offline_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
        if decoded.returncode != 0:
            raise RuntimeError("archive decoding failed")
        with path.open("rb") as stream:
            fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
        result.update(
            archive_validated=True, archive_bytes=path.stat().st_size, archive_sha256=fingerprint
        )
    except Exception:
        result["failure_stage"] = stage
    return result


async def backup_database(dsn, path, dump, restore, *, connect=None, run=subprocess.run):
    result = {
        "backup_status": "not_configured",
        "connection_attempted": False,
        "connection_established": False,
        "read_only_transaction_confirmed": False,
        "rollback_confirmed": False,
        "backup_created": False,
        "archive_validated": False,
        "pg_dump_connection_attempted": False,
        "application_account_records_read": False,
        "restore_tested": False,
        "migrations_applied": False,
        "checks": {},
        "live_activation_ready": False,
    }
    if not dsn:
        return result
    connection = transaction = None
    stage = "configuration"
    try:
        env = backup_environment(dsn)
        if connect is None:
            import asyncpg

            connect = asyncpg.connect
        stage = "connect"
        result["connection_attempted"] = True
        connection = await connect(
            dsn=dsn,
            timeout=5,
            command_timeout=5,
            server_settings={"default_transaction_read_only": "on"},
        )
        result["connection_established"] = True
        stage = "snapshot"
        transaction = connection.transaction(isolation="repeatable_read", readonly=True)
        await transaction.start()
        if await connection.fetchval("SHOW transaction_read_only") != "on":
            result["backup_status"] = "read_only_guard_failed"
            return result
        result["read_only_transaction_confirmed"] = True
        heads = [
            row["version_num"]
            for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
        ]
        if heads != [BASE]:
            result["backup_status"] = "database_head_changed"
            return result
        snapshot = await connection.fetchval("SELECT pg_export_snapshot()")
        stage = "archive"
        archive = await asyncio.to_thread(
            write_archive, path, dump, restore, env, snapshot, run=run
        )
        result.update(archive)
        result["backup_status"] = (
            "archive_created_and_validated" if archive["archive_validated"] else "failed"
        )
    except Exception:
        result.update(backup_status="unavailable", failure_stage=stage)
    finally:
        if transaction is not None:
            try:
                await asyncio.wait_for(transaction.rollback(), timeout=3)
                result["rollback_confirmed"] = True
            except Exception:
                result["backup_status"] = "rollback_not_confirmed"
        if connection is not None:
            try:
                await connection.close(timeout=2)
            except Exception:
                result["backup_status"] = "connection_cleanup_not_confirmed"
    return result
