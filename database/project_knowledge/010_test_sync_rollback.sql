-- Step 337: intentional transaction rollback test.
-- Execute ONLY against dubai_ai_knowledge_sync_test.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe test database';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 2
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected test baseline';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM project_knowledge.source_references
        WHERE source_path = 'core/rollback_probe_step337.py'
    ) THEN
        RAISE EXCEPTION 'Rollback probe already exists';
    END IF;
END
$preflight$;

INSERT INTO project_knowledge.source_references (
    project_id,
    reference_key,
    reference_type,
    source_path,
    description,
    content_sha256
)
SELECT
    id,
    'source:core/rollback_probe_step337.py',
    'source_file',
    'core/rollback_probe_step337.py',
    'Synthetic rollback probe',
    repeat('a', 64)
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id,
    source_path,
    content_sha256,
    size_bytes,
    source_reference_id
)
SELECT
    project_id,
    source_path,
    content_sha256,
    20,
    id
FROM project_knowledge.source_references
WHERE source_path = 'core/rollback_probe_step337.py';

-- Intentionally abort after both inserts.
DO $force_rollback$
BEGIN
    RAISE EXCEPTION 'STEP337_EXPECTED_ROLLBACK';
END
$force_rollback$;

COMMIT;
