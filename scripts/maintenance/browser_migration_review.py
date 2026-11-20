"""Restricted offline SQL generation for the two browser-auth migrations.

Uses an Alembic SQL-output context without an engine, URL, application imports,
environment loading or database connection. It never invokes downgrade.
"""

import ast
import io
import runpy
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

EXPECTED = {
    "0009_user_account_approval": "0008_tool_request_fingerprint",
    "0010_account_auth_storage": "0009_user_account_approval",
}
OPERATIONS = {
    "op.add_column",
    "op.create_foreign_key",
    "op.create_check_constraint",
    "op.alter_column",
    "op.create_unique_constraint",
    "op.create_table",
    "op.create_index",
    "op.f",
    "op.drop_constraint",
    "op.drop_column",
    "op.drop_index",
    "op.drop_table",
    "sa.Column",
    "sa.String",
    "sa.Uuid",
    "sa.DateTime",
    "sa.PrimaryKeyConstraint",
    "sa.ForeignKeyConstraint",
    "sa.UniqueConstraint",
    "sa.CheckConstraint",
    "sa.text",
    "sa.func.now",
}


def _call_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise ValueError("unsupported migration expression")
    return ".".join([node.id, *reversed(parts)])


def validate_source(source, revision):
    if revision not in EXPECTED:
        raise ValueError("unsupported browser migration")
    tree = ast.parse(source)
    metadata = {}
    functions = set()
    for node in tree.body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, ast.Import):
            if [(item.name, item.asname) for item in node.names] != [("sqlalchemy", "sa")]:
                raise ValueError("unreviewed migration import")
        elif isinstance(node, ast.ImportFrom):
            valid = node.level == 0 and (
                node.module,
                [(item.name, item.asname) for item in node.names],
            ) in (
                ("__future__", [("annotations", None)]),
                ("alembic", [("op", None)]),
            )
            if not valid:
                raise ValueError("unreviewed migration import")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                raise ValueError("unsupported migration assignment")
            name = targets[0].id
            if (
                name not in {"revision", "down_revision", "branch_labels", "depends_on"}
                or name in metadata
            ):
                raise ValueError("unsupported migration metadata")
            if isinstance(node, ast.AnnAssign) and any(
                isinstance(item, ast.Call) for item in ast.walk(node.annotation)
            ):
                raise ValueError("unsupported migration annotation")
            metadata[name] = ast.literal_eval(node.value)
        elif isinstance(node, ast.FunctionDef):
            if (
                node.name not in {"upgrade", "downgrade"}
                or node.name in functions
                or node.decorator_list
                or node.args.args
                or node.args.posonlyargs
                or node.args.kwonlyargs
                or node.args.vararg
                or node.args.kwarg
            ):
                raise ValueError("unsupported migration function")
            if node.returns is not None and not (
                isinstance(node.returns, ast.Constant) and node.returns.value is None
            ):
                raise ValueError("unsupported migration return annotation")
            functions.add(node.name)
            for statement in node.body:
                if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                    raise ValueError("unsupported migration statement")
                if not _call_name(statement.value.func).startswith("op."):
                    raise ValueError("migration statement must be an Alembic operation")
                for item in ast.walk(statement):
                    if isinstance(item, ast.Call) and _call_name(item.func) not in OPERATIONS:
                        raise ValueError("unreviewed migration operation")
                    if isinstance(item, ast.Name) and item.id not in {"sa", "op"}:
                        raise ValueError("unreviewed migration reference")
                    if isinstance(item, (ast.Starred, ast.Lambda, ast.NamedExpr, ast.Subscript)):
                        raise ValueError("unsupported migration expression")
                    if isinstance(item, ast.keyword) and item.arg is None:
                        raise ValueError("unsupported migration keywords")
        else:
            raise ValueError("unreviewed top-level migration statement")
    if metadata != {
        "revision": revision,
        "down_revision": EXPECTED[revision],
        "branch_labels": None,
        "depends_on": None,
    }:
        raise ValueError("browser migration metadata mismatch")
    if functions != {"upgrade", "downgrade"}:
        raise ValueError("browser migration functions missing")
    return True


def emit_upgrade_sql(path, revision):
    path = Path(path)
    if path.is_symlink() or path.is_junction() or path.stat().st_size > 1048576:
        raise ValueError("invalid migration source")
    source = path.read_text(encoding="utf-8-sig")
    validate_source(source, revision)
    namespace = runpy.run_path(str(path))
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={
            "as_sql": True,
            "output_buffer": buffer,
            "literal_binds": True,
        },
    )
    with Operations.context(context):
        namespace["upgrade"]()
    return buffer.getvalue()


def assess_upgrade_sql(approval, storage):
    first = " ".join(approval.lower().split())
    second = " ".join(storage.lower().split())
    forbidden = ("insert ", "update ", "delete ", "truncate ", "drop ")
    statements = [part.strip().lower() for part in (approval + storage).split(";") if part.strip()]
    checks = {
        "no_upgrade_data_rewrite_or_drop": not any(
            statement.startswith(forbidden) for statement in statements
        ),
        "approval_fields_present": all(
            f"add column {name}" in first
            for name in ("approval_status", "approval_decided_by", "approval_decided_at")
        ),
        "existing_rows_not_backfilled": "add column approval_status varchar(16)" in first
        and "add column approval_status varchar(16) default" not in first,
        "pending_default_added_after_column": "alter column approval_status set default 'pending'"
        in first
        and first.find("add column approval_status")
        < first.find("alter column approval_status set default"),
        "approval_constraints_present": all(
            name in first
            for name in (
                "ck_users_account_approval_status",
                "ck_users_account_approval_decision",
                "fk_users_approval_decided_by_users",
            )
        ),
        "auth_tables_present": all(
            f"create table {name}" in second
            for name in ("user_external_identities", "account_sessions")
        ),
        "tenant_reference_constraints_present": all(
            name in second
            for name in (
                "uq_users_organization_id_id",
                "fk_external_identity_tenant_user",
                "fk_account_session_tenant_user",
            )
        )
        and second.count(
            "foreign key(organization_id, user_id) references users (organization_id, id)"
        )
        == 2,
        "identity_subject_unique": "uq_external_identity_tenant_subject" in second,
        "session_digest_unique_and_checked": "uq_account_session_token_digest" in second
        and "ck_account_session_digest_format" in second,
        "session_expiry_and_revocation_checked": all(
            name in second
            for name in (
                "ck_account_session_expiry",
                "ck_account_session_revocation",
                "ck_account_session_auth_method",
            )
        ),
    }
    return {
        "checks": checks,
        "offline_sql_checks_passed": all(checks.values()),
        "database_behavior_verified": False,
        "migration_applied": False,
        "live_activation_ready": False,
    }
