"""Prepare source-version SQL from a reviewed change report.

Does not connect to PostgreSQL or execute SQL.
Never deletes source history.
"""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"

REPORT = FOLDER / "source_change_report.json"
BASELINE = FOLDER / "source_versions_baseline.json"
OUTPUT = FOLDER / "008_incremental_source_sync.sql"

PROJECT = "dubai-real-estate-ai"

if OUTPUT.exists():
    raise RuntimeError("Sync SQL already exists; do not overwrite it.")

report = json.loads(REPORT.read_text(encoding="utf-8-sig"))
baseline = json.loads(BASELINE.read_text(encoding="utf-8-sig"))

if report.get("project_key") != PROJECT:
    raise RuntimeError("Report project mismatch")

if baseline.get("project_key") != PROJECT:
    raise RuntimeError("Baseline project mismatch")

if report.get("baseline_files") != len(baseline["files"]):
    raise RuntimeError("Baseline count mismatch")

added = report["added"]
modified = report["modified"]
missing = report["missing"]

if missing:
    raise RuntimeError("Missing files require manual review before synchronization.")

if not added and not modified:
    print("PASS: No changes to synchronize")
    print("No SQL generated and no database writes required.")
    raise SystemExit(0)

known = {item["source_path"]: item["sha256"] for item in baseline["files"]}

if len(known) != len(baseline["files"]):
    raise RuntimeError("Duplicate paths in baseline")

records = []
seen = set()

for item in added + modified:
    path = item["source_path"]
    parsed = PurePosixPath(path)

    if (
        not isinstance(path, str)
        or parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in path
        or path in seen
        or any(
            part.lower() in {".git", ".venv", "node_modules", "__pycache__", ".next", "backups"}
            for part in parsed.parts
        )
        or any(term in parsed.name.lower() for term in ("secret", "credential", "password"))
        or parsed.name.lower().startswith(".env")
    ):
        raise RuntimeError(f"Unsafe or duplicate path: {path}")

    seen.add(path)

    file = ROOT / path

    if not file.is_file() or file.is_symlink():
        raise RuntimeError(f"File unavailable: {path}")

    size = file.stat().st_size

    if size > 2_000_000:
        raise RuntimeError(f"Oversized file: {path}")

    digest = hashlib.sha256(file.read_bytes()).hexdigest()

    expected = item.get("sha256", item.get("current_sha256"))

    if digest != expected:
        raise RuntimeError(f"File changed since report: {path}")

    previous = known.get(path)

    if item in added:
        if previous is not None:
            raise RuntimeError(f"Added file already indexed: {path}")
    else:
        if previous != item["previous_sha256"]:
            raise RuntimeError(f"Previous fingerprint mismatch: {path}")

    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError(f"Invalid fingerprint: {path}")

    records.append(
        {
            "source_path": path,
            "sha256": digest,
            "size_bytes": size,
            "previous_sha256": previous,
        }
    )

payload = json.dumps(records, ensure_ascii=True, separators=(",", ":"))

delimiter = "$source_sync_payload$"

if delimiter in payload:
    raise RuntimeError("SQL delimiter collision")

sql = f"""-- Step 331: controlled incremental source synchronization
-- Contains fingerprints and file metadata, not source contents.
-- Do not execute without reviewing the change report.
-- Original source references and earlier versions are preserved.

BEGIN;

DO $verify_source_baseline$
DECLARE
    item jsonb;
    latest_hash text;
BEGIN
    FOR item IN
        SELECT value
        FROM jsonb_array_elements(
            {delimiter}{payload}{delimiter}::jsonb
        )
    LOOP
        SELECT v.content_sha256 INTO latest_hash
        FROM project_knowledge.source_versions AS v
        JOIN project_knowledge.projects AS p
            ON p.id = v.project_id
        WHERE p.project_key = '{PROJECT}'
          AND v.source_path = item->>'source_path'
        ORDER BY v.recorded_at DESC, v.id DESC
        LIMIT 1;

        IF latest_hash IS DISTINCT FROM
           (item->>'previous_sha256') THEN
            RAISE EXCEPTION
                'Source baseline mismatch for %',
                item->>'source_path';
        END IF;
    END LOOP;
END
$verify_source_baseline$;

INSERT INTO project_knowledge.source_references
    (
        project_id, reference_key, reference_type,
        source_path, description, content_sha256
    )
SELECT
    p.id,
    'source:' || (item->>'source_path'),
    'source_file',
    item->>'source_path',
    '.source file; ' || (item->>'size_bytes') || ' bytes',
    item->>'sha256'
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_array_elements(
    {delimiter}{payload}{delimiter}::jsonb
) AS item
WHERE p.project_key = '{PROJECT}'
  AND item->>'previous_sha256' IS NULL
ON CONFLICT (project_id, reference_key) DO NOTHING;

INSERT INTO project_knowledge.source_versions
    (
        project_id, source_path, content_sha256,
        size_bytes, source_reference_id
    )
SELECT
    p.id,
    item->>'source_path',
    item->>'sha256',
    (item->>'size_bytes')::bigint,
    s.id
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_array_elements(
    {delimiter}{payload}{delimiter}::jsonb
) AS item
LEFT JOIN project_knowledge.source_references AS s
    ON s.project_id = p.id
   AND s.reference_key = 'source:' || (item->>'source_path')
WHERE p.project_key = '{PROJECT}'
ON CONFLICT (project_id, source_path, content_sha256)
DO NOTHING;

COMMIT;
"""  # noqa: S608 -- Escaped JSON/fixed metadata in an offline SQL generator.

OUTPUT.write_text(sql, encoding="utf-8")

print("PASS: Incremental SQL prepared")
print("New files:", len(added))
print("Modified files:", len(modified))
print("SQL file:", OUTPUT)
print("SQL has NOT been executed.")
