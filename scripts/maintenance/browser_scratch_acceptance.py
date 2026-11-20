"""Exercise reviewed DDL in a synthetic schema inside an always-rolled-back transaction."""

import asyncio
import re
import secrets
from uuid import UUID

BASE = "0006_job_recovery_operations"
HEAD = "0010_account_auth_storage"


def prepare_scratch_sql(sql, schema):
    if re.fullmatch(r"step539_[0-9a-f]{24}", schema) is None:
        raise ValueError("invalid scratch schema name")
    clean = re.sub(r"(?m)^\s*--[^\n]*", "", sql)
    statements = [part.strip() for part in clean.split(";") if part.strip()]
    if not statements or statements[0].upper() != "BEGIN" or statements[-1].upper() != "COMMIT":
        raise ValueError("reviewed transaction envelope required")
    statements = statements[1:-1]
    if (
        sum(
            statement.lower().startswith("update public.alembic_version ")
            for statement in statements
        )
        != 4
    ):
        raise ValueError("four reviewed version updates required")
    for statement in statements:
        lower = statement.lower()
        if not lower.startswith(
            ("create table ", "create index ", "alter table ", "update public.alembic_version ")
        ):
            raise ValueError("unreviewed scratch operation")
        without_version = statement.replace("public.alembic_version", "alembic_version")
        if re.search(r"\bpublic\s*\.", without_version, re.IGNORECASE):
            raise ValueError("application schema references prohibited")
        # All DDL targets and references must remain unqualified and resolve
        # through the private search_path. Only version bookkeeping is rewritten.
        if not lower.startswith("update ") and re.search(
            r"\b(?:table|references|on)\s+[^\s(;,]+\.", lower
        ):
            raise ValueError("qualified DDL references prohibited")
    rewritten = [
        statement.replace("public.alembic_version", f'"{schema}".alembic_version')
        for statement in statements
    ]
    return ";\n".join(rewritten) + ";\n"


async def expect_rejection(connection, sql, arguments, expected_state):
    savepoint = connection.transaction()
    await savepoint.start()
    try:
        await connection.execute(sql, *arguments)
        return False
    except Exception as error:
        return getattr(error, "sqlstate", None) == expected_state
    finally:
        await savepoint.rollback()


async def exercise_upgrade(dsn, sql, *, connect=None, schema=None):
    schema = "step539_" + secrets.token_hex(12) if schema is None else schema
    prepared = prepare_scratch_sql(sql, schema)
    result = {
        "acceptance_status": "not_started",
        "connection_attempted": False,
        "connection_established": False,
        "scratch_migrations_exercised": False,
        "persistent_database_migrations_applied": False,
        "application_user_rows_read": False,
        "scratch_schema_removed": None,
        "public_migration_head_unchanged": None,
        "rollback_confirmed": False,
        "scratch_read_write_transaction_confirmed": False,
        "checks": {},
        "live_activation_ready": False,
    }
    if not dsn:
        result["acceptance_status"] = "not_configured"
        return result
    if connect is None:
        import asyncpg

        connect = asyncpg.connect
    connection = None
    transaction = None
    stage = "connect"
    before_heads = None
    try:
        result["connection_attempted"] = True
        connection = await connect(
            dsn=dsn,
            timeout=5,
            command_timeout=5,
            server_settings={
                "default_transaction_read_only": "on",
                "application_name": "browser_scratch_acceptance",
            },
        )
        result["connection_established"] = True
        stage = "base_preflight"
        before_heads = sorted(
            row["version_num"]
            for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
        )
        if before_heads != [BASE]:
            result["acceptance_status"] = "database_head_changed"
            return result
        if await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=$1)", schema
        ):
            result["acceptance_status"] = "scratch_name_collision"
            return result
        stage = "scratch_setup"
        transaction = connection.transaction(isolation="repeatable_read", readonly=False)
        await transaction.start()
        # asyncpg omits READ WRITE when readonly=False. Override the inherited
        # read-only default only inside this always-rolled-back transaction.
        await connection.execute("SET TRANSACTION READ WRITE")
        if await connection.fetchval("SHOW transaction_read_only") != "off":
            raise RuntimeError("scratch read-write transaction guard failed")
        result["scratch_read_write_transaction_confirmed"] = True
        await connection.execute("SET LOCAL lock_timeout = '2s'")
        await connection.execute("SET LOCAL statement_timeout = '5s'")
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET LOCAL search_path TO "{schema}", pg_catalog')
        if await connection.fetchval("SELECT current_schema()") != schema:
            raise RuntimeError("scratch search path guard failed")
        await connection.execute("""
CREATE TABLE organizations (id uuid PRIMARY KEY, is_active boolean NOT NULL DEFAULT true);
CREATE TABLE users (
    id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id),
    email varchar(254) NOT NULL, full_name varchar(200) NOT NULL, password_hash varchar(255),
    is_active boolean NOT NULL DEFAULT true, UNIQUE (organization_id,email)
);
CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY);
""")
        await connection.execute("INSERT INTO alembic_version(version_num) VALUES($1)", BASE)
        org, other_org, legacy, pending, other_user = [
            UUID(int=value) for value in (5391, 5392, 5393, 5394, 5395)
        ]
        await connection.execute("INSERT INTO organizations(id) VALUES($1),($2)", org, other_org)
        await connection.execute(
            "INSERT INTO users(id,organization_id,email,full_name) VALUES($1,$2,'legacy@example.invalid','Step539 synthetic legacy')",
            legacy,
            org,
        )
        stage = "upgrade_execution"
        await connection.execute(prepared)
        result["scratch_migrations_exercised"] = True
        stage = "constraint_acceptance"
        checks = result["checks"]
        checks["legacy_status_preserved_null"] = (
            await connection.fetchval(
                "SELECT approval_status IS NULL FROM users WHERE id=$1", legacy
            )
            is True
        )
        await connection.execute(
            "INSERT INTO users(id,organization_id,email,full_name) VALUES($1,$2,'pending@example.invalid','Step539 synthetic pending'),($3,$4,'other@example.invalid','Step539 synthetic other')",
            pending,
            org,
            other_user,
            other_org,
        )
        row = await connection.fetchrow(
            "SELECT approval_status,approval_decided_by,approval_decided_at FROM users WHERE id=$1",
            pending,
        )
        checks["new_user_defaults_pending"] = (
            row["approval_status"] == "pending"
            and row["approval_decided_by"] is None
            and row["approval_decided_at"] is None
        )
        checks["invalid_approval_status_rejected"] = await expect_rejection(
            connection,
            "UPDATE users SET approval_status='invalid' WHERE id=$1",
            (pending,),
            "23514",
        )
        checks["incomplete_approval_rejected"] = await expect_rejection(
            connection,
            "UPDATE users SET approval_status='approved' WHERE id=$1",
            (pending,),
            "23514",
        )
        await connection.execute(
            "UPDATE users SET approval_status='approved', approval_decided_by=$2, approval_decided_at=now() WHERE id=$1",
            pending,
            legacy,
        )
        checks["complete_approval_accepted"] = (
            await connection.fetchval("SELECT approval_status FROM users WHERE id=$1", pending)
            == "approved"
        )
        identity_sql = "INSERT INTO user_external_identities(id,organization_id,user_id,issuer,subject) VALUES($1,$2,$3,$4,$5)"
        await connection.execute(
            identity_sql,
            UUID(int=5401),
            org,
            pending,
            "https://accounts.google.com",
            "step539-subject",
        )
        checks["valid_google_identity_accepted"] = True
        identity_cases = (
            (
                "foreign_tenant_identity_rejected",
                5402,
                other_user,
                "https://accounts.google.com",
                "foreign",
                "23503",
            ),
            (
                "duplicate_google_subject_rejected",
                5403,
                legacy,
                "https://accounts.google.com",
                "step539-subject",
                "23505",
            ),
            (
                "wrong_google_issuer_rejected",
                5404,
                pending,
                "https://invalid.example",
                "issuer",
                "23514",
            ),
            (
                "empty_google_subject_rejected",
                5405,
                pending,
                "https://accounts.google.com",
                "   ",
                "23514",
            ),
        )
        for name, identifier, user, issuer, subject, state in identity_cases:
            checks[name] = await expect_rejection(
                connection, identity_sql, (UUID(int=identifier), org, user, issuer, subject), state
            )
        session_sql = "INSERT INTO account_sessions(id,organization_id,user_id,token_digest,auth_method,issued_at,expires_at,revoked_at) VALUES($1,$2,$3,$4,$5,now(),now()+($6::int * interval '1 second'),CASE WHEN $7::int IS NULL THEN NULL ELSE now()+($7::int * interval '1 second') END)"
        await connection.execute(
            session_sql, UUID(int=5501), org, pending, "a" * 64, "google", 3600, None
        )
        checks["valid_hashed_session_accepted"] = True
        session_cases = (
            (
                "foreign_tenant_session_rejected",
                5502,
                other_user,
                "b" * 64,
                "google",
                3600,
                None,
                "23503",
            ),
            (
                "malformed_digest_rejected",
                5503,
                pending,
                "not-a-digest",
                "google",
                3600,
                None,
                "23514",
            ),
            ("duplicate_digest_rejected", 5504, pending, "a" * 64, "google", 3600, None, "23505"),
            (
                "invalid_auth_method_rejected",
                5505,
                pending,
                "c" * 64,
                "invalid",
                3600,
                None,
                "23514",
            ),
            (
                "expired_session_interval_rejected",
                5506,
                pending,
                "d" * 64,
                "google",
                -60,
                None,
                "23514",
            ),
            (
                "invalid_revocation_time_rejected",
                5507,
                pending,
                "e" * 64,
                "google",
                3600,
                -60,
                "23514",
            ),
        )
        for name, identifier, user, digest, method, expiry, revocation, state in session_cases:
            checks[name] = await expect_rejection(
                connection,
                session_sql,
                (UUID(int=identifier), org, user, digest, method, expiry, revocation),
                state,
            )
        checks["scratch_version_reached_head"] = (
            await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
        )
        checks["fingerprint_remains_nullable"] = (
            await connection.fetchval(
                "SELECT is_nullable FROM information_schema.columns WHERE table_schema=$1 AND table_name='tool_execution_ledger' AND column_name='request_fingerprint'",
                schema,
            )
            == "YES"
        )
        checks["foreign_keys_stay_inside_scratch"] = (
            await connection.fetchval(
                "SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_class r ON r.oid=c.confrelid JOIN pg_namespace rn ON rn.oid=r.relnamespace WHERE c.contype='f' AND n.nspname=$1 AND rn.nspname<>$1",
                schema,
            )
            == 0
        )
        result["acceptance_status"] = (
            "passed_pending_rollback" if all(checks.values()) else "constraint_checks_failed"
        )
    except Exception as error:
        result["acceptance_status"] = "unavailable_or_failed"
        result["failure_stage"] = stage
        state = getattr(error, "sqlstate", None)
        result["failure_code"] = (
            state
            if state
            in {
                "42501",
                "42P06",
                "42703",
                "42P01",
                "23503",
                "23505",
                "23514",
                "25006",
                "55P03",
                "57014",
            }
            else "unclassified"
        )
    finally:
        if transaction is not None:
            try:
                await asyncio.wait_for(transaction.rollback(), timeout=5)
                result["rollback_confirmed"] = True
            except Exception:
                result["rollback_confirmed"] = False
                result["acceptance_status"] = "rollback_not_confirmed"
        if connection is not None:
            try:
                if transaction is not None and result["rollback_confirmed"]:
                    result["scratch_schema_removed"] = not await connection.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=$1)", schema
                    )
                    after_heads = sorted(
                        row["version_num"]
                        for row in await connection.fetch(
                            "SELECT version_num FROM public.alembic_version"
                        )
                    )
                    result["public_migration_head_unchanged"] = after_heads == before_heads
                    if (
                        not result["scratch_schema_removed"]
                        or not result["public_migration_head_unchanged"]
                    ):
                        result["acceptance_status"] = "cleanup_postcondition_failed"
            except Exception:
                result["acceptance_status"] = "cleanup_postcondition_unverified"
            finally:
                try:
                    await connection.close(timeout=2)
                except Exception:
                    result["connection_close_confirmed"] = False
                    result["acceptance_status"] = "connection_close_unconfirmed"
    if result["acceptance_status"] == "passed_pending_rollback" and result["rollback_confirmed"]:
        result["acceptance_status"] = "passed_and_rolled_back"
    return result
