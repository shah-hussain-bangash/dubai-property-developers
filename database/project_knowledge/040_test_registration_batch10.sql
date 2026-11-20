
-- Step 373: second batch, rollback-only.
BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 411
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 411
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 411
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 411
    THEN
        RAISE EXCEPTION 'Unexpected Step 373 baseline';
    END IF;
END
$guard$;

CREATE TEMP TABLE step416_batch (
    source_path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO step416_batch VALUES
('background_jobs_migration_review.sql', 'd94500cdbc856903706239452bd151283fe145397c185a10c18cf91b34cd5292', 60120),
('integrations/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('integrations/bayut/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('integrations/espocrm/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('integrations/factory.py', 'ac3cebe54248c75907840b55597edb67a20356f873c738ad6f3c62b8d55d7e26', 4155),
('integrations/google/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('integrations/listing_portal.py', 'd23f3ae2d2754bf20932263286d43ab135f2934fd1fe3de44540fd78b8c2296e', 1798),
('integrations/meta/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('integrations/n8n/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('integrations/propertyfinder/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0);

DO $preflight$
DECLARE
    v_project UUID;
BEGIN
    SELECT id INTO STRICT v_project
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF (SELECT COUNT(*) FROM step416_batch) <> 10 THEN
        RAISE EXCEPTION 'Invalid batch count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM step416_batch b
        WHERE EXISTS (
            SELECT 1 FROM project_knowledge.source_references r
            WHERE r.project_id = v_project AND r.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_versions v
            WHERE v.project_id = v_project AND v.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_change_events e
            WHERE e.project_id = v_project AND e.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_current_state s
            WHERE s.project_id = v_project AND s.source_path = b.source_path
        )
    ) THEN
        RAISE EXCEPTION 'Batch contains existing registrations';
    END IF;
END
$preflight$;

INSERT INTO project_knowledge.source_references (
    project_id, reference_key, reference_type,
    source_path, description, content_sha256
)
SELECT
    p.id, 'source:' || b.source_path, 'source_file',
    b.source_path, 'Step 410 rollback-only test',
    b.content_sha256
FROM step416_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id, source_path, content_sha256,
    size_bytes, source_reference_id
)
SELECT
    p.id, b.source_path, b.content_sha256, b.size_bytes, r.id
FROM step416_batch b
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
SELECT
    p.id, b.source_path, NULL, b.content_sha256, 'added'
FROM step416_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_current_state (
    project_id, source_path, current_sha256
)
SELECT p.id, b.source_path, b.content_sha256
FROM step416_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

DO $verify$
DECLARE
    v_valid BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 421
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 421
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 421
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 421
    THEN
        RAISE EXCEPTION 'Unexpected test counts';
    END IF;

    SELECT COUNT(*) INTO v_valid
    FROM step416_batch b
    JOIN project_knowledge.source_references r
      ON r.source_path = b.source_path
     AND r.reference_key = 'source:' || b.source_path
     AND r.content_sha256 = b.content_sha256
    JOIN project_knowledge.source_versions v
      ON v.source_reference_id = r.id
     AND v.project_id = r.project_id
     AND v.source_path = b.source_path
     AND v.content_sha256 = b.content_sha256
     AND v.size_bytes = b.size_bytes
    JOIN project_knowledge.source_change_events e
      ON e.project_id = r.project_id
     AND e.source_path = b.source_path
     AND e.current_sha256 = b.content_sha256
     AND e.previous_sha256 IS NULL
     AND e.event_type = 'added'
    JOIN project_knowledge.source_current_state s
      ON s.project_id = r.project_id
     AND s.source_path = b.source_path
     AND s.current_sha256 = b.content_sha256;

    IF v_valid <> 10 THEN
        RAISE EXCEPTION 'Batch integrity failed: %', v_valid;
    END IF;

    IF (
        SELECT COUNT(*)
        FROM project_knowledge.source_change_events
        WHERE event_type = 'initial'
    ) <> 325
    OR (
        SELECT COUNT(*)
        FROM project_knowledge.source_change_events
        WHERE event_type = 'added'
    ) <> 96
    THEN
        RAISE EXCEPTION 'Unexpected event types';
    END IF;

    RAISE NOTICE 'PASS: All ten tenth-batch registrations validated';
    RAISE NOTICE 'PASS: Four-table integrity and history verified';
END
$verify$;

ROLLBACK;
