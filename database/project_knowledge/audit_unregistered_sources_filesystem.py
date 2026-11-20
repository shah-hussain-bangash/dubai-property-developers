"""Step 361.1: audit unregistered local project files without Git."""

import csv
import io
import os
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = "dubai_ai_knowledge_verify_20261019_095633"

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    ".tox",
    "backups",
    "test_logs",
    "reports",
    ".idea",
    ".vscode",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".dump",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".zip",
    ".tar",
    ".gz",
    ".bak",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
}

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".rst",
    ".html",
    ".css",
    ".scss",
    ".sh",
    ".ps1",
    ".ini",
    ".cfg",
}


def fetch_registry():
    sql = """
    COPY (
        SELECT source_path
        FROM project_knowledge.source_versions
        WHERE project_id = (
            SELECT id
            FROM project_knowledge.projects
            WHERE project_key = 'dubai-real-estate-ai'
        )
        ORDER BY source_path
    ) TO STDOUT WITH (FORMAT CSV);
    """

    result = subprocess.run(  # noqa: S603 -- Trusted local executable and argument list; no shell or request input.
        [  # noqa: S607 -- Local maintenance tool resolves Docker from the operator PATH.
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dubai_ai",
            "-d",
            DB,
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    rows = csv.reader(io.StringIO(result.stdout))

    registry = {row[0].replace("\\", "/") for row in rows if row}

    if len(registry) != 325:
        raise RuntimeError(f"Unexpected registry baseline: {len(registry)}")

    return registry


def classify(path):
    suffix = Path(path).suffix.lower()

    if suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".sql", ".json", ".yaml", ".yml", ".toml"}:
        return "code_or_configuration"

    if suffix in {".md", ".rst"}:
        return "documentation"

    return "other"


def discover_files():
    discovered = []

    for directory, subdirs, filenames in os.walk(ROOT, topdown=True, followlinks=False):
        parent = Path(directory)

        subdirs[:] = [
            name
            for name in subdirs
            if name.lower() not in EXCLUDED_DIRS and not (parent / name).is_symlink()
        ]

        for filename in filenames:
            target = parent / filename

            if filename.lower().startswith(".env"):
                continue

            if target.is_symlink() or not target.is_file():
                continue

            suffix = target.suffix.lower()

            if suffix in EXCLUDED_SUFFIXES:
                continue

            if suffix not in SOURCE_SUFFIXES:
                continue

            relative = target.relative_to(ROOT).as_posix()

            discovered.append(
                {
                    "source_path": relative,
                    "category": classify(relative),
                    "size_bytes": target.stat().st_size,
                }
            )

    return discovered


def main():
    registry = fetch_registry()
    local_files = discover_files()

    missing_from_registry = [row for row in local_files if row["source_path"] not in registry]

    missing_from_registry.sort(key=lambda row: row["source_path"])

    counts = Counter(row["category"] for row in missing_from_registry)

    report_dir = ROOT / "database" / "project_knowledge" / "reports"

    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = report_dir / (f"step361_filesystem_unregistered_{stamp}.csv")

    with report.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["source_path", "category", "size_bytes"],
        )

        writer.writeheader()
        writer.writerows(missing_from_registry)

    print("PASS: Database registry retrieved")
    print("Registered source records:", len(registry))
    print("Local candidate source files:", len(local_files))
    print("Unregistered candidates:", len(missing_from_registry))

    for category in (
        "code_or_configuration",
        "documentation",
        "other",
    ):
        print(f"{category}: {counts[category]}")

    print("\nFirst 30 unregistered candidates:")

    for row in missing_from_registry[:30]:
        print(row["category"], row["source_path"])

    print("\nReport:", report)
    print("PASS: Step 361.1 filesystem audit completed")


if __name__ == "__main__":
    main()
