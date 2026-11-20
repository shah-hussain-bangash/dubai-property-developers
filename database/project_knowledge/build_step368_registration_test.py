"""Build a rollback-only registration test from Step 367's manifest."""

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "database/project_knowledge/reports/step367_registration_batch.csv"
OUTPUT = ROOT / "database/project_knowledge/022_test_registration_batch.sql"
DB = "dubai_ai_knowledge_verify_20261019_095633"


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Step 368 SQL already exists. Stop.")

    with MANIFEST.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))

    if len(rows) != 10:
        raise RuntimeError("Expected exactly 10 manifest entries")

    if len({row["source_path"] for row in rows}) != 10:
        raise RuntimeError("Duplicate paths")

    values = []

    for row in rows:
        path = row["source_path"]
        sha = row["sha256"]

        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or ":" in path
            or any(p in ("", ".", "..") for p in path.split("/"))
        ):
            raise RuntimeError(f"Unsafe path: {path}")

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise RuntimeError(f"Invalid fingerprint: {path}")

        if (
            row["status"] != "ready_for_isolated_test"
            or row["approved_for_live_registration"] != "false"
        ):
            raise RuntimeError(f"Unexpected approval state: {path}")

        target = ROOT.joinpath(*path.split("/"))
        target.resolve(strict=True).relative_to(ROOT.resolve())

        current = ROOT
        for component in path.split("/"):
            current = current / component
            if current.is_symlink():
                raise RuntimeError(f"Symlink rejected: {path}")

        data = target.read_bytes()

        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError(f"Fingerprint changed: {path}")

        if len(data) != int(row["size_bytes"]):
            raise RuntimeError(f"File size changed: {path}")

        values.append(f"({sql_quote(path)}, {sql_quote(sha)}, {len(data)})")

    sql = r"""
-- Step 368: temporary 10-file registration test.
-- All test inserts are rolled back.
BEGIN;

DO $guard$
BEGIN
    IF current_database() <> '__TARGET_DB__' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 325
    THEN
        RAISE EXCEPTION 'Unexpected registration baseline';
    END IF;
END
$guard$;

CREATE TEMP TABLE step368_batch (
    source_path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO step368_batch VALUES
__VALUES__;

DO $guard$
DECLARE
    v_project UUID;
BEGIN
    SELECT id INTO STRICT v_project
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF (SELECT COUNT(*) FROM step368_batch) <> 10 THEN
        RAISE EXCEPTION 'Invalid batch count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM step368_batch b
        WHERE EXISTS (
            SELECT 1 FROM project_knowledge.source_references r
            WHERE r.project_id = v_project AND r.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_versions v
            WHERE v.project_id = v_project AND v.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_current_state s
            WHERE s.project_id = v_project AND s.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_change_events e
            WHERE e.project_id = v_project AND e.source_path = b.source_path
        )
    ) THEN
        RAISE EXCEPTION 'One or more batch files already registered';
    END IF;
END
$guard$;

INSERT INTO project_knowledge.source_references (
    project_id, reference_key, reference_type,
    source_path, description, content_sha256
)
SELECT
    p.id, 'source:' || b.source_path, 'source_file',
    b.source_path, 'Step 368 rollback-only registration test',
    b.content_sha256
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id, source_path, content_sha256,
    size_bytes, source_reference_id
)
SELECT p.id, b.source_path, b.content_sha256,
       b.size_bytes, r.id
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
JOIN project_knowledge.source_references r
  ON r.project_id = p.id
 AND r.source_path = b.source_path
 AND r.reference_key = 'source:' || b.source_path
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_change_events (
    project_id, source_path, previous_sha256,
    current_sha256, event_type
)
SELECT p.id, b.source_path, NULL,
       b.content_sha256, 'added'
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_current_state (
    project_id, source_path, current_sha256
)
SELECT p.id, b.source_path, b.content_sha256
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

DO $verify$
DECLARE
    v_good BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 335
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 335
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 335
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 335
    THEN
        RAISE EXCEPTION 'Unexpected test counts';
    END IF;

    SELECT COUNT(*) INTO v_good
    FROM step368_batch b
    JOIN project_knowledge.source_references r
      ON r.source_path = b.source_path
     AND r.content_sha256 = b.content_sha256
    JOIN project_knowledge.source_versions v
      ON v.source_reference_id = r.id
     AND v.project_id = r.project_id
     AND v.source_path = b.source_path
     AND v.content_sha256 = b.content_sha256
     AND v.size_bytes = b.size_bytes
    JOIN project_knowledge.source_current_state s
      ON s.project_id = r.project_id
     AND s.source_path = b.source_path
     AND s.current_sha256 = b.content_sha256
    JOIN project_knowledge.source_change_events e
      ON e.project_id = r.project_id
     AND e.source_path = b.source_path
     AND e.current_sha256 = b.content_sha256
     AND e.previous_sha256 IS NULL
     AND e.event_type = 'added';

    IF v_good <> 10 THEN
        RAISE EXCEPTION 'Registration link/hash validation failed: %', v_good;
    END IF;

    RAISE NOTICE 'PASS: All ten registrations valid within transaction';
    RAISE NOTICE 'PASS: Four-table links and SHA-256 values verified';
END
$verify$;

-- Never commit this test batch.
ROLLBACK;
""".replace("__TARGET_DB__", DB).replace("__VALUES__", ",\n".join(values))

    OUTPUT.write_text(sql, encoding="utf-8")
    print("PASS: All 10 files rehashed and validated")
    print("PASS: Rollback-only SQL generated")
    print("SQL:", OUTPUT)


if __name__ == "__main__":
    main()
