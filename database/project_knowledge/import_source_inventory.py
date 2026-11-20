"""Prepare a validated PostgreSQL source-reference import."""

import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"

SOURCE = FOLDER / "source_inventory.json"
DESTINATION = FOLDER / "003_import_source_inventory.sql"

PROJECT_KEY = "dubai-real-estate-ai"

ALLOWED_EXTENSIONS = {
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
    ".ini",
}

if DESTINATION.exists():
    raise RuntimeError("SQL import already exists. Review it before regenerating.")

inventory = json.loads(SOURCE.read_text(encoding="utf-8"))

if inventory.get("project_key") != PROJECT_KEY:
    raise ValueError("Project identity mismatch")

records = inventory.get("files")

if not isinstance(records, list) or not 0 < len(records) <= 10000:
    raise ValueError("Invalid source inventory size")

seen = set()
validated = []

for record in records:
    path = record["source_path"]
    extension = record["extension"]
    size = record["size_bytes"]
    digest = record["sha256"]

    if not isinstance(path, str):
        raise ValueError("Invalid source path")

    parsed = PurePosixPath(path)

    if not path or parsed.is_absolute() or "\\" in path or ".." in parsed.parts or path in seen:
        raise ValueError(f"Unsafe or duplicate source path: {path}")

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported extension: {extension}")

    if parsed.suffix.lower() != extension:
        raise ValueError("File extension mismatch")

    if not isinstance(size, int) or not 0 <= size <= 2000000:
        raise ValueError("Invalid file size")

    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid SHA-256 digest")

    seen.add(path)

    validated.append(
        {
            "reference_key": "source:" + path,
            "reference_type": "source_file",
            "source_path": path,
            "description": f"{extension} source file; {size} bytes",
            "content_sha256": digest,
        }
    )

# SQL string escaping, including any unusual path characters.
payload = json.dumps(
    validated,
    ensure_ascii=True,
    separators=(",", ":"),
).replace("'", "''")

sql = f"""-- Validated source inventory import
-- Project: {PROJECT_KEY}
-- Metadata and hashes only; no source code contents.
-- Safe to rerun without duplicating existing references.

BEGIN;

DO $verify_project$
BEGIN
    IF (
        SELECT count(*)
        FROM project_knowledge.projects
        WHERE project_key = '{PROJECT_KEY}'
    ) <> 1 THEN
        RAISE EXCEPTION 'Expected project is missing';
    END IF;
END
$verify_project$;

INSERT INTO project_knowledge.source_references
    (
        project_id,
        reference_key,
        reference_type,
        source_path,
        description,
        content_sha256
    )
SELECT
    p.id,
    incoming.reference_key,
    incoming.reference_type,
    incoming.source_path,
    incoming.description,
    incoming.content_sha256
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_to_recordset(
    '{payload}'::jsonb
) AS incoming(
    reference_key text,
    reference_type text,
    source_path text,
    description text,
    content_sha256 text
)
WHERE p.project_key = '{PROJECT_KEY}'
ON CONFLICT (project_id, reference_key) DO NOTHING;

COMMIT;
"""  # noqa: S608 -- Escaped JSON/fixed metadata in an offline SQL generator.

DESTINATION.write_text(sql, encoding="utf-8")

print("PASS: Validated SQL import created")
print("Project:", PROJECT_KEY)
print("Validated source references:", len(validated))
print("SQL file:", DESTINATION)
print("No source-code contents included")
