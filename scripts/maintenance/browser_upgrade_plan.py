"""Render the observed 0006 -> 0010 upgrade in an isolated offline Alembic env."""

import ast
import io
import re
import runpy
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

BASE = "0006_job_recovery_operations"
CHAIN = (
    "0007_tool_execution_ledger",
    "0008_tool_request_fingerprint",
    "0009_user_account_approval",
    "0010_account_auth_storage",
)
ENV_SOURCE = """from alembic import context
if not context.is_offline_mode():
    raise RuntimeError("Only offline SQL generation is supported")
context.configure(dialect_name="postgresql", literal_binds=True,
                  version_table_schema="public")
with context.begin_transaction():
    context.run_migrations()
"""


def _call_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise ValueError("unsupported migration call")
    return ".".join([node.id, *reversed(parts)])


def verify_json_variant(source):
    values = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "JsonType" for target in node.targets
        ):
            values.append(ast.dump(node.value))
    expected = ast.dump(ast.parse('JSON().with_variant(JSONB(), "postgresql")', mode="eval").body)
    if values != [expected]:
        raise ValueError("the shared PostgreSQL JSON variant requires review")
    return True


def reviewed_offline_source(path, revision, *, allowed_calls):
    path = Path(path)
    if (
        revision not in CHAIN
        or path.is_symlink()
        or path.is_junction()
        or path.stat().st_size > 1048576
    ):
        raise ValueError("unsupported migration source")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
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
            signature = (node.module, [(item.name, item.asname) for item in node.names])
            if node.level:
                raise ValueError("unreviewed relative import")
            if signature == ("database.base", [("JsonType", None)]) and revision == CHAIN[0]:
                # The repository's JSON-with-PostgreSQL-JSONB variant renders as
                # JSONB here. Adapt only this import in the temporary copy.
                node.module = "sqlalchemy.dialects.postgresql"
                node.names = [ast.alias(name="JSONB", asname="JsonType")]
            elif signature not in (
                ("__future__", [("annotations", None)]),
                ("alembic", [("op", None)]),
            ):
                raise ValueError("unreviewed migration import")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                raise ValueError("unsupported migration metadata")
            name = targets[0].id
            if (
                name not in {"revision", "down_revision", "branch_labels", "depends_on"}
                or name in metadata
            ):
                raise ValueError("unsupported migration metadata")
            if isinstance(node, ast.AnnAssign) and any(
                isinstance(item, ast.Call) for item in ast.walk(node.annotation)
            ):
                raise ValueError("unreviewed migration annotation")
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
                raise ValueError("unsupported migration annotation")
            functions.add(node.name)
            for statement in node.body:
                if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                    raise ValueError("unsupported migration statement")
                if not _call_name(statement.value.func).startswith("op."):
                    raise ValueError("unsupported migration operation")
                for item in ast.walk(statement):
                    if isinstance(item, ast.Call) and _call_name(item.func) not in allowed_calls:
                        raise ValueError("unreviewed migration call")
                    if isinstance(item, ast.Name) and item.id not in {"sa", "op", "JsonType"}:
                        raise ValueError("unreviewed migration reference")
                    if isinstance(item, (ast.Starred, ast.Lambda, ast.NamedExpr, ast.Subscript)):
                        raise ValueError("unsupported migration expression")
                    if isinstance(item, ast.keyword) and item.arg is None:
                        raise ValueError("unsupported migration keyword expansion")
        else:
            raise ValueError("unreviewed top-level migration statement")
    position = CHAIN.index(revision)
    expected = {
        "revision": revision,
        "down_revision": BASE if position == 0 else CHAIN[position - 1],
        "branch_labels": None,
        "depends_on": None,
    }
    if metadata != expected or functions != {"upgrade", "downgrade"}:
        raise ValueError("upgrade chain metadata mismatch")
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


def assess_range_sql(sql):
    clean = re.sub(r"(?m)^\s*--[^\n]*", "", sql)
    statements = [part.strip().lower() for part in clean.split(";") if part.strip()]
    updates = [item for item in statements if item.startswith("update ")]
    forbidden = [
        item for item in statements if item.startswith(("drop ", "delete ", "insert ", "truncate "))
    ]
    transitions = list(zip((BASE, *CHAIN[:-1]), CHAIN, strict=True))
    version_steps = all(
        any(
            f"set version_num='{target}'" in statement
            and f"where public.alembic_version.version_num = '{source}'" in statement
            for statement in updates
        )
        for source, target in transitions
    )
    lower = clean.lower()
    checks = {
        "single_transaction": bool(statements)
        and statements[0] == "begin"
        and statements[-1] == "commit"
        and statements.count("begin") == 1
        and statements.count("commit") == 1,
        "four_version_updates_only": len(updates) == 4
        and all(statement.startswith("update public.alembic_version ") for statement in updates)
        and version_steps,
        "no_user_data_rewrite_or_drop": not forbidden
        and not any(
            item.startswith("update ") and not item.startswith("update public.alembic_version ")
            for item in statements
        ),
        "ledger_before_fingerprint": "create table tool_execution_ledger" in lower
        and "alter table tool_execution_ledger add column request_fingerprint" in lower
        and lower.index("create table tool_execution_ledger")
        < lower.index("add column request_fingerprint"),
        "postgresql_jsonb_preserved": "result_json jsonb" in lower,
        "approval_before_auth_storage": "add column approval_status" in lower
        and "create table account_sessions" in lower
        and lower.index("add column approval_status")
        < lower.index("create table account_sessions"),
        "auth_identity_table_present": "create table user_external_identities" in lower,
        "approval_default_after_nullable_column": "add column approval_status varchar(16) default"
        not in lower
        and "alter column approval_status set default 'pending'" in lower,
        "tenant_constraints_present": all(
            name in lower
            for name in (
                "fk_account_session_tenant_user",
                "fk_external_identity_tenant_user",
                "uq_external_identity_tenant_subject",
            )
        ),
    }
    return {
        "checks": checks,
        "offline_plan_checks_passed": all(checks.values()),
        "database_behavior_verified": False,
        "database_migrations_applied": False,
        "live_activation_ready": False,
    }


def build_upgrade_plan(project_root, observed_heads):
    if observed_heads != [BASE]:
        raise ValueError("the plan requires a verified single 0006 migration head")
    root = Path(project_root).resolve()
    verify_json_variant((root / "database/base.py").read_text(encoding="utf-8-sig"))
    review = runpy.run_path(str(root / "scripts/maintenance/browser_migration_review.py"))
    originals = {
        revision: root / f"database/migrations/versions/{revision}.py" for revision in CHAIN
    }
    temporary_sources = {
        revision: reviewed_offline_source(path, revision, allowed_calls=review["OPERATIONS"])
        for revision, path in originals.items()
    }
    output = io.StringIO()
    with tempfile.TemporaryDirectory(prefix="browser-upgrade-review-") as folder:
        temporary = Path(folder)
        versions = temporary / "versions"
        versions.mkdir()
        (temporary / "env.py").write_text(ENV_SOURCE, encoding="utf-8")
        # Metadata-only anchor for an already-applied revision. Its functions
        # are never run because offline generation starts at this revision.
        (versions / "base_anchor.py").write_text(
            f"revision = {BASE!r}\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n",
            encoding="utf-8",
        )
        for revision, source in temporary_sources.items():
            (versions / f"{revision}.py").write_text(source, encoding="utf-8")
        config = Config(output_buffer=output)
        config.set_main_option("script_location", str(temporary))
        command.upgrade(config, f"{BASE}:{CHAIN[-1]}", sql=True)
    sql = output.getvalue()
    assessment = assess_range_sql(sql)
    if not assessment["offline_plan_checks_passed"]:
        raise ValueError("offline upgrade plan failed review")
    return {
        "base_revision": BASE,
        "target_revision": CHAIN[-1],
        "pending_revisions": list(CHAIN),
        "sql": sql,
        "assessment": assessment,
        "database_connections": 0,
        "existing_migration_sources_modified": False,
        "database_migrations_applied": False,
    }
