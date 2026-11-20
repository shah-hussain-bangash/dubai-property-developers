"""Inspect upgrade prerequisites using catalogs only; never execute migration SQL."""

import asyncio

BASE = "0006_job_recovery_operations"
RELATIONS = (
    "tool_execution_ledger",
    "pk_tool_execution_ledger",
    "uq_tool_execution_ledger_org_key",
    "ix_tool_execution_ledger_organization_id",
    "ix_tool_execution_ledger_org_state",
    "user_external_identities",
    "pk_user_external_identities",
    "uq_external_identity_tenant_subject",
    "ix_external_identity_tenant_user",
    "account_sessions",
    "pk_account_sessions",
    "uq_account_session_token_digest",
    "ix_account_session_tenant_user",
    "ix_account_session_expiry",
    "uq_users_organization_id_id",
)
COLUMNS = ("approval_status", "approval_decided_by", "approval_decided_at")
CONSTRAINTS = (
    "fk_users_approval_decided_by_users",
    "ck_users_account_approval_status",
    "ck_users_account_approval_decision",
    "uq_users_organization_id_id",
)
CATALOG_SQL = """
SELECT
  has_schema_privilege('public', 'USAGE') AND has_schema_privilege('public', 'CREATE') AS schema_access,
  has_table_privilege('public.alembic_version', 'SELECT')
    AND has_table_privilege('public.alembic_version', 'UPDATE') AS version_access,
  has_column_privilege('public.organizations', 'id', 'REFERENCES') AS organization_reference,
  (SELECT count(*) = 2 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname IN ('users','organizations')
     AND c.relkind='r' AND NOT c.relispartition AND NOT c.relhassubclass) AS ordinary_tables,
  (SELECT pg_has_role(c.relowner, 'USAGE') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname='users') AS users_owner,
  (SELECT count(*) = 3 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
   JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND ((c.relname IN ('users','organizations') AND a.attname='id')
     OR (c.relname='users' AND a.attname='organization_id'))
     AND a.atttypid='uuid'::regtype AND a.attnotnull AND NOT a.attisdropped) AS baseline_columns,
  (SELECT count(*) = 2 FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
   JOIN pg_namespace n ON n.oid=c.relnamespace
   JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='id'
   WHERE n.nspname='public' AND c.relname IN ('users','organizations')
     AND k.contype='p' AND k.conkey=ARRAY[a.attnum] AND k.convalidated) AS primary_keys,
  EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='public' AND c.relname=ANY($1::text[])) AS relation_collision,
  EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
         WHERE n.nspname='public' AND t.typname=ANY($1::text[])) AS type_collision,
  EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
         JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
         AND c.relname='users' AND a.attname=ANY($2::text[]) AND NOT a.attisdropped) AS column_collision,
  EXISTS(SELECT 1 FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
         JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
         AND c.relname='users' AND k.conname=ANY($3::text[])) AS constraint_collision,
  EXISTS(SELECT 1 FROM pg_locks l JOIN pg_class c ON c.oid=l.relation
         JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
         AND c.relname IN ('users','organizations','alembic_version')
         AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
         AND l.pid IS DISTINCT FROM pg_backend_pid()) AS other_relation_locks
"""
REQUIRED = (
    "schema_access",
    "version_access",
    "organization_reference",
    "ordinary_tables",
    "users_owner",
    "baseline_columns",
    "primary_keys",
)
ABSENT = (
    "relation_collision",
    "type_collision",
    "column_collision",
    "constraint_collision",
    "other_relation_locks",
)


def assess_catalog(row):
    # Do not return catalog names, role names, SQL, rows or arbitrary driver values.
    checks = {key: row.get(key) is True for key in REQUIRED}
    checks.update({key: row.get(key) is False for key in ABSENT})
    return checks


async def inspect_upgrade(dsn, *, connect=None):
    result = {
        "preflight_status": "not_configured",
        "connection_attempted": False,
        "connection_established": False,
        "read_only_transaction_confirmed": False,
        "rollback_confirmed": False,
        "checks": {},
        "application_account_records_read": False,
        "migrations_applied": False,
        "live_activation_ready": False,
        "existing_data_migration_compatibility_proven": False,
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
                "application_name": "browser_upgrade_preflight",
            },
        )
        result["connection_established"] = True
        stage = "transaction"
        transaction = connection.transaction(isolation="repeatable_read", readonly=True)
        await transaction.start()
        if await connection.fetchval("SHOW transaction_read_only") != "on":
            result["preflight_status"] = "read_only_guard_failed"
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
            result["preflight_status"] = "database_head_changed"
            return result
        stage = "catalog_checks"
        row = await connection.fetchrow(
            CATALOG_SQL, list(RELATIONS), list(COLUMNS), list(CONSTRAINTS)
        )
        result["checks"] = assess_catalog(dict(row))
        result["preflight_status"] = (
            "catalog_preflight_passed" if all(result["checks"].values()) else "blocked"
        )
    except Exception:
        result.update(preflight_status="unavailable", failure_stage=stage)
    finally:
        if transaction is not None:
            try:
                await asyncio.wait_for(transaction.rollback(), timeout=3)
                result["rollback_confirmed"] = True
            except Exception:
                result["preflight_status"] = "rollback_not_confirmed"
        if connection is not None:
            try:
                await connection.close(timeout=2)
            except Exception:
                result["preflight_status"] = "connection_cleanup_not_confirmed"
    return result
