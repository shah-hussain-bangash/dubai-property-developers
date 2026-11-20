"""Read-only PostgreSQL catalog inspection. Never applies migrations or reads users."""

import asyncio
from contextlib import suppress

from sqlalchemy.engine import make_url

KNOWN_REVISIONS = {
    "0001_initial_schema",
    "0002_lead_persistence",
    "0003_unique_lead_dedupe_keys",
    "0004_background_job_tracking",
    "0005_job_outbox",
    "0006_job_recovery_operations",
    "0007_tool_execution_ledger",
    "0008_tool_request_fingerprint",
    "0009_user_account_approval",
    "0010_account_auth_storage",
}
EXPECTED_HEAD = "0010_account_auth_storage"
REQUIRED_COLUMNS = {
    "organizations": {"id", "is_active"},
    "users": {
        "id",
        "organization_id",
        "email",
        "full_name",
        "password_hash",
        "is_active",
        "approval_status",
        "approval_decided_by",
        "approval_decided_at",
    },
    "roles": {"id", "name"},
    "user_roles": {"user_id", "role_id"},
    "user_external_identities": {"id", "organization_id", "user_id", "issuer", "subject"},
    "account_sessions": {
        "id",
        "organization_id",
        "user_id",
        "token_digest",
        "auth_method",
        "issued_at",
        "expires_at",
        "revoked_at",
    },
    "audit_logs": {
        "id",
        "organization_id",
        "actor",
        "action",
        "resource_type",
        "resource_id",
        "outcome",
        "details",
    },
}
KEY_CONSTRAINTS = {
    "uq_users_organization_id_id": ("users", "u", ["organization_id", "id"], None, []),
    "fk_external_identity_tenant_user": (
        "user_external_identities",
        "f",
        ["organization_id", "user_id"],
        "users",
        ["organization_id", "id"],
    ),
    "fk_account_session_tenant_user": (
        "account_sessions",
        "f",
        ["organization_id", "user_id"],
        "users",
        ["organization_id", "id"],
    ),
    "uq_external_identity_tenant_subject": (
        "user_external_identities",
        "u",
        ["organization_id", "issuer", "subject"],
        None,
        [],
    ),
    "uq_account_session_token_digest": ("account_sessions", "u", ["token_digest"], None, []),
    "fk_users_approval_decided_by_users": ("users", "f", ["approval_decided_by"], "users", ["id"]),
}
CHECK_CONSTRAINTS = {
    "ck_users_account_approval_status": "users",
    "ck_users_account_approval_decision": "users",
    "ck_external_identity_google_issuer": "user_external_identities",
    "ck_external_identity_nonempty_subject": "user_external_identities",
    "ck_account_session_digest_format": "account_sessions",
    "ck_account_session_auth_method": "account_sessions",
    "ck_account_session_expiry": "account_sessions",
    "ck_account_session_revocation": "account_sessions",
}
COLUMNS_SQL = """
SELECT table_name, column_name, data_type, is_nullable, character_maximum_length
FROM information_schema.columns
WHERE table_schema = $1 AND table_name = ANY($2::text[])
"""
CONSTRAINTS_SQL = """
SELECT c.conname AS name, t.relname AS table_name, c.contype::text AS kind,
       c.convalidated AS validated, n2.nspname AS referenced_schema,
       t2.relname AS referenced_table, c.confdeltype::text AS delete_action,
       ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY AS k(num, pos)
             JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num ORDER BY k.pos) AS columns,
       ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY AS k(num, pos)
             JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.num ORDER BY k.pos) AS referenced_columns
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_class t2 ON t2.oid = c.confrelid
LEFT JOIN pg_namespace n2 ON n2.oid = t2.relnamespace
WHERE n.nspname = $1 AND c.conname = ANY($2::text[])
"""


def connect_dsn(database_url):
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("database configuration missing")
    try:
        url = make_url(database_url)
        if (
            url.drivername != "postgresql+asyncpg"
            or not url.host
            or not url.database
            or any(key != "sslmode" for key in url.query)
        ):
            raise ValueError("unsupported database configuration")
        _port = url.port
        if "sslmode" in url.query and url.query["sslmode"] not in {
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        }:
            raise ValueError("unsupported SSL mode")
        return url.set(drivername="postgresql").render_as_string(hide_password=False)
    except Exception:
        raise ValueError("database URL format unsupported") from None


def assess_metadata(columns, constraints, applied_heads):
    found = {(row["table_name"], row["column_name"]): row for row in columns}
    missing = {
        table: sorted(name for name in names if (table, name) not in found)
        for table, names in REQUIRED_COLUMNS.items()
    }
    missing = {table: names for table, names in missing.items() if names}
    types = {}
    for table, names in REQUIRED_COLUMNS.items():
        for name in names:
            row = found.get((table, name))
            if row is None:
                continue
            kind = row["data_type"]
            valid = True
            if name in {"id", "organization_id", "user_id", "role_id", "approval_decided_by"}:
                valid = kind == "uuid"
            elif name == "is_active":
                valid = kind == "boolean"
            elif name in {"issued_at", "expires_at", "revoked_at", "approval_decided_at"}:
                valid = kind == "timestamp with time zone"
            elif name == "details":
                valid = kind in {"json", "jsonb"}
            else:
                valid = kind == "character varying"
            nullable = (table, name) in {
                ("users", "password_hash"),
                ("users", "approval_status"),
                ("users", "approval_decided_by"),
                ("users", "approval_decided_at"),
                ("account_sessions", "revoked_at"),
                ("audit_logs", "resource_id"),
            }
            valid = valid and row["is_nullable"] == ("YES" if nullable else "NO")
            if table == "account_sessions":
                nullable = name == "revoked_at"
                valid = valid and (row["is_nullable"] == ("YES" if nullable else "NO"))
                if name in {"token_digest", "auth_method"}:
                    valid = valid and row["character_maximum_length"] == (
                        64 if name == "token_digest" else 16
                    )
            if table == "users" and name in {
                "approval_status",
                "approval_decided_by",
                "approval_decided_at",
            }:
                valid = valid and row["is_nullable"] == "YES"
                if name == "approval_status":
                    valid = valid and row["character_maximum_length"] == 16
            types[f"{table}.{name}"] = "compatible" if valid else "mismatch"
    by_name = {}
    for row in constraints:
        by_name.setdefault(row["name"], []).append(row)
    keys = {}
    for name, (table, kind, expected, reference, referenced_columns) in KEY_CONSTRAINTS.items():
        matches = by_name.get(name, [])
        valid = len(matches) == 1
        if valid:
            row = matches[0]
            valid = (
                row["table_name"] == table
                and row["kind"] == kind
                and row["validated"] is True
                and list(row["columns"]) == expected
            )
            if reference is not None:
                valid = (
                    valid
                    and row["referenced_schema"] == "public"
                    and row["referenced_table"] == reference
                    and list(row["referenced_columns"]) == referenced_columns
                    and row["delete_action"]
                    == ("r" if name == "fk_users_approval_decided_by_users" else "c")
                )
        keys[name] = "matches" if valid else "missing_or_mismatch"
    checks = {}
    for name, table in CHECK_CONSTRAINTS.items():
        matches = by_name.get(name, [])
        checks[name] = (
            "present_and_validated"
            if (
                len(matches) == 1
                and matches[0]["table_name"] == table
                and matches[0]["kind"] == "c"
                and matches[0]["validated"] is True
            )
            else "missing_or_mismatch"
        )
    safe_heads = [head if head in KNOWN_REVISIONS else "unrecognized" for head in applied_heads]
    head_matches = applied_heads == [EXPECTED_HEAD]
    compatible = (
        not missing
        and all(value == "compatible" for value in types.values())
        and all(value == "matches" for value in keys.values())
        and all(value == "present_and_validated" for value in checks.values())
        and head_matches
    )
    return {
        "missing_columns": missing,
        "column_metadata": types,
        "key_constraints": keys,
        "check_constraints": checks,
        "applied_migration_heads": safe_heads,
        "expected_migration_head_applied": head_matches,
        "catalog_metadata_compatible": compatible,
        "check_constraint_definitions_verified": False,
        "constraint_behavior_verified": False,
        "live_activation_ready": False,
    }


async def inspect_database(database_url, *, connect=None):
    base = {
        "inspection_status": "not_configured",
        "connection_attempted": False,
        "connection_established": False,
        "read_only_transaction_confirmed": False,
        "data_writes_performed": False,
        "migrations_applied": False,
        "live_activation_ready": False,
    }
    if not database_url:
        return base
    try:
        dsn = connect_dsn(database_url)
    except ValueError:
        return {**base, "inspection_status": "unsupported_database_configuration"}
    if connect is None:
        import asyncpg

        connect = asyncpg.connect
    connection = None
    transaction = None
    stage = "connect"
    base["connection_attempted"] = True
    try:
        connection = await connect(
            dsn=dsn,
            timeout=5,
            command_timeout=5,
            server_settings={
                "default_transaction_read_only": "on",
                "application_name": "browser_schema_inspection",
            },
        )
        base["connection_established"] = True
        stage = "transaction"
        transaction = connection.transaction(isolation="repeatable_read", readonly=True)
        await transaction.start()
        if await connection.fetchval("SHOW transaction_read_only") != "on":
            return {**base, "inspection_status": "read_only_guard_failed"}
        base["read_only_transaction_confirmed"] = True
        stage = "catalog_query"
        columns = await connection.fetch(
            COLUMNS_SQL, "public", [*REQUIRED_COLUMNS, "alembic_version"]
        )
        constraints = await connection.fetch(
            CONSTRAINTS_SQL, "public", [*KEY_CONSTRAINTS, *CHECK_CONSTRAINTS]
        )
        has_version = any(
            row["table_name"] == "alembic_version" and row["column_name"] == "version_num"
            for row in columns
        )
        heads = (
            sorted(
                row["version_num"]
                for row in await connection.fetch("SELECT version_num FROM public.alembic_version")
            )
            if has_version
            else []
        )
        return {
            **base,
            "inspection_status": "completed",
            "metadata": assess_metadata(columns, constraints, heads),
        }
    except (TimeoutError, Exception):
        # Driver messages can include URLs, passwords, hostnames, or server details.
        return {**base, "inspection_status": "unavailable", "failure_stage": stage}
    finally:
        if transaction is not None:
            with suppress(Exception):
                await asyncio.wait_for(transaction.rollback(), timeout=2)
        if connection is not None:
            with suppress(Exception):
                await connection.close(timeout=2)
