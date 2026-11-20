"""Compare project source files against the PostgreSQL baseline.

Read-only: no database writes and no changes to source files.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from database.project_knowledge.contracts import SourceFingerprint

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"

BASELINE = FOLDER / "source_versions_baseline.json"
OUTPUT = FOLDER / "source_change_report.json"

PROJECT_KEY = "dubai-real-estate-ai"

SCAN_DIRECTORIES = (
    "apps",
    "core",
    "database/migrations",
    "database/models",
    "database/repositories",
    "tests",
    "agents",
    "workflows",
)

ROOT_FILES = (
    "pyproject.toml",
    "alembic.ini",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".sql",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
}

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".next",
    "backups",
    "dist",
    "build",
    "coverage",
}

MAX_BYTES = 2_000_000
MAX_FILES = 10000


def safe_path(relative: str) -> bool:
    path = PurePosixPath(relative)

    return (
        bool(relative)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in relative
        and not any(part.lower() in EXCLUDED_PARTS for part in path.parts)
        and not any(term in path.name.lower() for term in ("secret", "credential", "password"))
        and not path.name.lower().startswith(".env")
        and not path.name.lower().endswith(".bak")
    )


def eligible(file: Path) -> bool:
    if not file.is_file() or file.is_symlink():
        return False

    relative = file.relative_to(ROOT).as_posix()

    if not safe_path(relative):
        return False

    if file.suffix.lower() not in EXTENSIONS and file.name not in ROOT_FILES:
        return False

    return file.stat().st_size <= MAX_BYTES


def fingerprint(file: Path) -> SourceFingerprint:
    digest = hashlib.sha256()

    with file.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            digest.update(chunk)

    return {
        "source_path": file.relative_to(ROOT).as_posix(),
        "sha256": digest.hexdigest(),
        "size_bytes": file.stat().st_size,
    }


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Change report already exists. Review before replacing.")

    baseline = json.loads(BASELINE.read_text(encoding="utf-8-sig"))

    if baseline.get("project_key") != PROJECT_KEY:
        raise RuntimeError("Baseline project mismatch")

    baseline_files = baseline.get("files")

    if not isinstance(baseline_files, list):
        raise RuntimeError("Invalid baseline file list")

    if len(baseline_files) != baseline.get("source_count"):
        raise RuntimeError("Baseline count mismatch")

    known = {}

    for item in baseline_files:
        path = item["source_path"]
        digest = item["sha256"]

        if not safe_path(path):
            raise RuntimeError(f"Unsafe baseline path: {path}")

        if path in known:
            raise RuntimeError(
                f"Multiple baseline versions for path: {path}. A latest-version export is required."
            )

        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise RuntimeError(f"Invalid baseline hash: {path}")

        known[path] = item

    candidates: set[Path] = set()

    for folder_name in SCAN_DIRECTORIES:
        folder = ROOT / folder_name

        if folder.is_dir() and not folder.is_symlink():
            candidates.update(folder.rglob("*"))

    for filename in ROOT_FILES:
        path = ROOT / filename

        if path.is_file():
            candidates.add(path)

    current = {}

    for file in candidates:
        if eligible(file):
            item = fingerprint(file)
            current[item["source_path"]] = item

    if len(current) > MAX_FILES:
        raise RuntimeError("File safety limit exceeded")

    added = []
    modified = []
    unchanged = []
    missing = []

    for path, item in sorted(current.items()):
        old = known.get(path)

        if old is None:
            added.append(item)

        elif old["sha256"] != item["sha256"]:
            modified.append(
                {
                    "source_path": path,
                    "previous_sha256": old["sha256"],
                    "current_sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
            )

        else:
            unchanged.append(path)

    for path in sorted(set(known) - set(current)):
        missing.append(path)

    report: dict[str, Any] = {
        "project_key": PROJECT_KEY,
        "baseline_files": len(known),
        "current_files": len(current),
        "summary": {
            "added": len(added),
            "modified": len(modified),
            "unchanged": len(unchanged),
            "missing": len(missing),
        },
        "added": added,
        "modified": modified,
        "missing": missing,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("PASS: Source change detection completed")
    print("Baseline files:", len(known))
    print("Current files:", len(current))
    print("Summary:", report["summary"])
    print("Report:", OUTPUT)

    for category in ("added", "modified", "missing"):
        records = report[category]

        if records:
            print("\n" + category.upper() + ":")

            for item in records[:30]:
                path = item if isinstance(item, str) else item["source_path"]
                print(" ", path)


if __name__ == "__main__":
    main()
