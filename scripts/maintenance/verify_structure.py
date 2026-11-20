"""Verify the monorepo layout and that every Python package imports.

Usage: python scripts/maintenance/verify_structure.py
Exit code 1 if a required path is missing or a module fails to import.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = [
    "apps/api/app/main.py",
    "apps/api/Dockerfile",
    "apps/dashboard/package.json",
    "apps/dashboard/Dockerfile",
    "apps/worker/main.py",
    "apps/worker/Dockerfile",
    "workflows/lead_flow.py",
    "workflows/qualification_flow.py",
    "workflows/property_flow.py",
    "workflows/sales_flow.py",
    "workflows/followup_flow.py",
    "workflows/customer_support_flow.py",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "pyproject.toml",
    "docker-compose.yml",
    "Makefile",
    "README.md",
    "ARCHITECTURE.md",
    "CLAUDE.md",
    "alembic.ini",
]
REQUIRED_DIRS = [
    *(
        f"agents/{a}"
        for a in (
            "supervisor",
            "lead_intake",
            "qualification",
            "property_recommendation",
            "sales_conversation",
            "followup",
            "crm",
            "email",
            "whatsapp",
            "voice",
            "marketing",
            "documents",
            "analytics",
        )
    ),
    *(
        f"core/{c}"
        for c in (
            "config",
            "llm",
            "memory",
            "policies",
            "security",
            "observability",
            "exceptions",
            "events",
        )
    ),
    *(
        f"tools/{t}"
        for t in (
            "crm",
            "whatsapp",
            "email",
            "calendar",
            "property",
            "documents",
            "search",
            "analytics",
        )
    ),
    *(
        f"integrations/{i}"
        for i in (
            "espocrm",
            "meta",
            "google",
            "propertyfinder",
            "bayut",
            "telephony",
            "n8n",
            "slack",
        )
    ),
    *(
        f"schemas/{s}"
        for s in ("leads", "properties", "conversations", "agents", "integrations", "events")
    ),
    *(f"database/{d}" for d in ("models", "migrations", "repositories", "seeds", "sessions")),
    *(
        f"knowledge/{k}"
        for k in ("ingestion", "retrieval", "embeddings", "vectorstores", "documents", "evaluation")
    ),
    *(
        f"tests/{t}"
        for t in ("unit", "integration", "agents", "workflows", "security", "evaluations")
    ),
    "scripts/setup",
    "scripts/maintenance",
    "scripts/development",
    *(
        f"docs/{d}"
        for d in ("architecture", "api", "agents", "deployment", "security", "development")
    ),
    "docker/postgres",
    "docker/redis",
    "docker/monitoring",
    ".github/workflows",
    ".vscode",
]
PACKAGES = [
    "apps",
    "agents",
    "core",
    "tools",
    "integrations",
    "schemas",
    "database",
    "knowledge",
    "workflows",
]


def main() -> int:
    errors = [f"missing file: {p}" for p in REQUIRED if not (ROOT / p).is_file()]
    errors += [f"missing dir: {d}" for d in REQUIRED_DIRS if not (ROOT / d).is_dir()]
    sys.path.insert(0, str(ROOT))
    imported = 0
    for name in PACKAGES:
        package = importlib.import_module(name)
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{name}."):
            if info.name.startswith("apps.api.app.main"):
                continue  # importing main builds the app; covered by tests
            try:
                importlib.import_module(info.name)
                imported += 1
            except Exception as exc:
                errors.append(f"import failed: {info.name}: {type(exc).__name__}: {exc}")
    for error in errors:
        print(error)
    print(f"checked {len(REQUIRED)} files, {len(REQUIRED_DIRS)} dirs, imported {imported} modules")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
