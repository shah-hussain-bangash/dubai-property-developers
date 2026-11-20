"""Create a metadata-only inventory of project source files."""

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRECTORIES = (
    "apps",
    "core",
    "database/migrations",
    "database/models",
    "database/repositories",
    "tests",
)

SCAN_FILES = (
    "pyproject.toml",
    "alembic.ini",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".sql", ".md", ".yaml", ".yml", ".toml",
}

EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "node_modules",
    "backups", "__pycache__", ".pytest_cache",
    "dist", "build", "coverage", ".next",
}

MAX_FILE_BYTES = 2_000_000


def safe_file(path):
    if not path.is_file() or path.is_symlink():
        return False

    relative = path.relative_to(ROOT)

    if any(
        part.lower() in EXCLUDED_PARTS
        for part in relative.parts
    ):
        return False

    name = path.name.lower()

    if (
        name.startswith(".env")
        or "secret" in name
        or "credential" in name
        or "password" in name
        or name.endswith(".bak")
    ):
        return False

    if not (
        path.suffix.lower() in EXTENSIONS
        or name in SCAN_FILES
    ):
        return False

    return path.stat().st_size <= MAX_FILE_BYTES


def inspect_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            digest.update(chunk)

    return {
        "source_path": path.relative_to(ROOT).as_posix(),
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def main():
    candidates = []

    for name in SCAN_DIRECTORIES:
        folder = ROOT / name

        if folder.is_dir():
            candidates.extend(folder.rglob("*"))

    for name in SCAN_FILES:
        path = ROOT / name

        if path.is_file():
            candidates.append(path)

    files = []

    for path in sorted(set(candidates)):
        if safe_file(path):
            files.append(inspect_file(path))

    if len(files) > 10000:
        raise RuntimeError("Inventory safety limit exceeded")

    output = {
        "project_key": "dubai-real-estate-ai",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "inventory_version": 1,
        "files": files,
    }

    destination = (
        ROOT
        / "database"
        / "project_knowledge"
        / "source_inventory.json"
    )

    if destination.exists():
        raise RuntimeError(
            "Inventory exists. Do not overwrite automatically."
        )

    destination.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    counts = Counter(
        item["extension"]
        for item in files
    )

    print("PASS: Source inventory created")
    print("Total files:", len(files))
    print("File types:", dict(counts))
    print("Output:", destination)

    print("\nAgent-related source files:")

    for item in files:
        path = item["source_path"]

        if "agent" in path.lower():
            print(path)


if __name__ == "__main__":
    main()
