"""Offline readiness inspection. Never executes migrations or connects clients.

Only status codes, environment key names, and migration identifiers are returned.
Successful offline checks do not prove database state or allow live activation.
"""

import ast
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ENV_KEYS = (
    "BROWSER_AUTH_TRUSTED_ORIGIN",
    "BROWSER_AUTH_ORGANIZATION_ID",
    "BROWSER_AUTH_OWNER_ID",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "BROWSER_AUTH_CSRF_SECRET",
    "BROWSER_AUTH_SESSION_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
    "AUTH_MODE",
    "ENABLE_DEV_ROUTES",
    "BROWSER_AUTH_REGISTRATION_ENABLED",
)
REQUIRED_REVISIONS = ("0009_user_account_approval", "0010_account_auth_storage")
STAGED = {
    "0009_user_account_approval": "database/migrations/reviewed/0009_user_account_approval.py",
    "0010_account_auth_storage": "database/migrations/reviewed/0010_account_auth_storage.py",
}
SCHEMA_COLUMNS = {
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


def _placeholder(value):
    return any(
        marker in value.casefold()
        for marker in (
            "change-me",
            "changeme",
            "replace-me",
            "placeholder",
            "synthetic-",
            "your-secret",
        )
    )


def inspect_environment(values):
    checks = {}
    for key in ENV_KEYS:
        if key == "BROWSER_AUTH_REGISTRATION_ENABLED":
            value = values.get(key, "false")
        else:
            value = values.get(key)
        if not isinstance(value, str) or not value.strip():
            checks[key] = "missing"
            continue
        valid = True
        try:
            if key in {"BROWSER_AUTH_ORGANIZATION_ID", "BROWSER_AUTH_OWNER_ID"}:
                valid = UUID(value).int != 0
            elif key == "BROWSER_AUTH_TRUSTED_ORIGIN":
                parsed = urlsplit(value)
                _port = parsed.port
                valid = (
                    value.isascii()
                    and parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and parsed.username is None
                    and parsed.password is None
                    and not parsed.path
                    and not parsed.query
                    and not parsed.fragment
                    and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
                )
            elif key in {"BROWSER_AUTH_CSRF_SECRET", "BROWSER_AUTH_SESSION_SECRET"}:
                valid = len(value.encode("utf-8")) >= 32 and not _placeholder(value)
            elif key in {"GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"}:
                valid = len(value) <= 4096 and not _placeholder(value)
            elif key in {"DATABASE_URL", "REDIS_URL"}:
                parsed = urlsplit(value)
                _port = parsed.port
                schemes = {"postgresql+asyncpg"} if key == "DATABASE_URL" else {"redis", "rediss"}
                valid = (
                    parsed.scheme in schemes
                    and bool(parsed.hostname)
                    and not parsed.fragment
                    and not any(c.isspace() or ord(c) < 32 for c in value)
                )
                if key == "DATABASE_URL":
                    valid = valid and bool(parsed.path.strip("/"))
            elif key == "AUTH_MODE":
                valid = value == "token"
            elif key in {"ENABLE_DEV_ROUTES", "BROWSER_AUTH_REGISTRATION_ENABLED"}:
                valid = value.casefold() == "false"
        except (ValueError, UnicodeError):
            valid = False
        checks[key] = "format_ok" if valid else "invalid_or_unsafe"
    csrf = values.get("BROWSER_AUTH_CSRF_SECRET")
    session = values.get("BROWSER_AUTH_SESSION_SECRET")
    if isinstance(csrf, str) and csrf == session:
        for key in ("BROWSER_AUTH_CSRF_SECRET", "BROWSER_AUTH_SESSION_SECRET"):
            checks[key] = "must_be_distinct"
    return {
        "checks": checks,
        "configuration_format_ready": all(status == "format_ok" for status in checks.values()),
        "credential_authenticity_verified": False,
        "connections_tested": False,
        "live_activation_ready": False,
    }


def _migration_metadata(path):
    if path.is_symlink() or path.is_junction() or path.stat().st_size > 1048576:
        raise ValueError("invalid migration source")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    fields = {}
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                if target.id in fields:
                    raise ValueError("duplicate migration metadata")
                fields[target.id] = ast.literal_eval(node.value)
    if set(fields) != {"revision", "down_revision"}:
        raise ValueError("missing migration metadata")
    for name, value in fields.items():
        if name == "down_revision" and value is None:
            continue
        if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_]{1,128}", value) is None:
            raise ValueError("invalid migration metadata")
    return fields["revision"], fields["down_revision"]


def inspect_migrations(project_root):
    root = Path(project_root).resolve()
    directory = root / "database/migrations/versions"
    revisions = {}
    graph_valid = directory.is_dir() and not directory.is_symlink() and not directory.is_junction()
    parse_failures = 0
    if graph_valid:
        for path in sorted(directory.glob("*.py")):
            if path.name == "__init__.py":
                continue
            try:
                revision, parent = _migration_metadata(path)
                if revision in revisions:
                    graph_valid = False
                revisions[revision] = parent
            except (OSError, ValueError, TypeError, SyntaxError):
                graph_valid = False
                parse_failures += 1
    heads = set(revisions) - {parent for parent in revisions.values() if parent is not None}
    graph_valid = graph_valid and bool(revisions) and len(heads) == 1
    for revision in revisions:
        seen = set()
        current = revision
        while current is not None:
            if current in seen or current not in revisions:
                graph_valid = False
                break
            seen.add(current)
            current = revisions[current]
    staged = {}
    expected_parents = {
        REQUIRED_REVISIONS[0]: "0008_tool_request_fingerprint",
        REQUIRED_REVISIONS[1]: REQUIRED_REVISIONS[0],
    }
    for revision, relative in STAGED.items():
        path = root / relative
        try:
            metadata = _migration_metadata(path)
            staged[revision] = (
                "metadata_matches"
                if metadata == (revision, expected_parents[revision])
                else "metadata_mismatch"
            )
        except (OSError, ValueError, TypeError, SyntaxError):
            staged[revision] = "missing_or_invalid"
    required = {
        revision: "registered" if revision in revisions else "missing"
        for revision in REQUIRED_REVISIONS
    }
    for revision, parent in expected_parents.items():
        if revision in revisions and revisions[revision] != parent:
            graph_valid = False
    return {
        "migration_graph_valid": graph_valid,
        "active_migration_count": len(revisions),
        "parse_failures": parse_failures,
        "active_heads": sorted(heads),
        "required_revisions": required,
        "staged_candidates": staged,
        "required_migrations_registered": graph_valid
        and all(status == "registered" for status in required.values()),
        "migration_source_executed": False,
        "migrations_applied": False,
        "database_schema_verified": False,
        "live_activation_ready": False,
    }


def assess_schema_columns(snapshot):
    """Compare externally collected metadata. Presence alone does not verify constraints."""
    missing = {}
    for table, required in SCHEMA_COLUMNS.items():
        columns = snapshot.get(table, ()) if isinstance(snapshot, dict) else ()
        found = set(columns) if isinstance(columns, (set, frozenset, list, tuple)) else set()
        absent = required - found
        if absent:
            missing[table] = sorted(absent)
    return {
        "required_columns_present": not missing,
        "missing_columns": missing,
        "constraints_verified": False,
        "types_and_nullability_verified": False,
        "live_activation_ready": False,
    }
