"""Import missing agent/workflow source metadata without changing old records."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"
SOURCE = FOLDER / "source_inventory.json"
OUTPUT = FOLDER / "006_import_missing_sources.sql"

PROJECT_KEY = "dubai-real-estate-ai"
MAX_SIZE = 2_000_000

if OUTPUT.exists():
    raise RuntimeError("Import SQL already exists. Stop.")

inventory = json.loads(SOURCE.read_text(encoding="utf-8"))

if inventory.get("project_key") != PROJECT_KEY:
    raise RuntimeError("Project key mismatch")

known = {}

for record in inventory["files"]:
    path = record["source_path"]
    if path in known:
        raise RuntimeError("Duplicate existing inventory path")
    known[path] = record

# Refuse an import if the original snapshot is no longer current.
for path, record in known.items():
    file = ROOT / path

    if not file.is_file() or file.is_symlink():
        raise RuntimeError(f"Previously indexed file missing: {path}")

    actual_hash = hashlib.sha256(file.read_bytes()).hexdigest()

    if actual_hash != record["sha256"]:
        raise RuntimeError(f"Previously indexed file changed: {path}")

new_records = []

for directory in ("agents", "workflows"):
    folder = ROOT / directory

    if not folder.is_dir() or folder.is_symlink():
        raise RuntimeError(f"Missing source directory: {directory}")

    for file in sorted(folder.rglob("*.py")):
        if not file.is_file() or file.is_symlink() or "__pycache__" in file.parts:
            continue

        relative = file.relative_to(ROOT).as_posix()

        if relative in known:
            continue

        size = file.stat().st_size

        if size > MAX_SIZE:
            raise RuntimeError(f"Oversized source file: {relative}")

        digest = hashlib.sha256(file.read_bytes()).hexdigest()

        new_records.append(
            {
                "reference_key": "source:" + relative,
                "reference_type": "source_file",
                "source_path": relative,
                "description": f".py source file; {size} bytes",
                "content_sha256": digest,
            }
        )

if len(new_records) != 61:
    raise RuntimeError(
        f"Expected 61 missing source files; found {len(new_records)}. "
        "Stop and review changes before proceeding."
    )

payload = json.dumps(
    new_records,
    ensure_ascii=True,
    separators=(",", ":"),
)

delimiter = "$missing_sources_payload$"

if delimiter in payload:
    raise RuntimeError("Unexpected SQL delimiter collision")

sql = f"""-- Step 327: add missing source references.
-- Does not change existing records or application tables.

BEGIN;

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
    item->>'reference_key',
    item->>'reference_type',
    item->>'source_path',
    item->>'description',
    item->>'content_sha256'
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_array_elements(
    {delimiter}{payload}{delimiter}::jsonb
) AS item
WHERE p.project_key = '{PROJECT_KEY}'
ON CONFLICT (project_id, reference_key) DO NOTHING;

DO $verify_count$
DECLARE
    actual_count integer;
BEGIN
    SELECT COUNT(*) INTO actual_count
    FROM project_knowledge.source_references AS s
    JOIN project_knowledge.projects AS p
      ON p.id = s.project_id
    WHERE p.project_key = '{PROJECT_KEY}'
      AND s.reference_type = 'source_file';

    IF actual_count <> 325 THEN
        RAISE EXCEPTION
            'Expected 325 source references; found %',
            actual_count;
    END IF;
END
$verify_count$;

COMMIT;
"""  # noqa: S608 -- Escaped JSON/fixed metadata in an offline SQL generator.

OUTPUT.write_text(sql, encoding="utf-8")

print("PASS: Incremental source import prepared")
print("Previously indexed:", len(known))
print("New source files:", len(new_records))
print("Expected database total:", len(known) + len(new_records))
print("SQL file:", OUTPUT)
