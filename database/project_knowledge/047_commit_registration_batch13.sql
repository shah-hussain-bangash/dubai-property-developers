
-- Step 373: second batch, rollback-only.
BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 441
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 441
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 441
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 441
    THEN
        RAISE EXCEPTION 'Unexpected Step 373 baseline';
    END IF;
END
$guard$;

CREATE TEMP TABLE step434_batch (
    source_path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO step434_batch VALUES
('schemas/conversations/models.py', '54b711d918ea7bd2af546323e83cd81fd830775b35d8a8eaf7fddb1b26edb236', 1440),
('schemas/events/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('schemas/events/models.py', '0850872f3fcc3f90310b5714714b3b1637878315f1f88592283613e0f98376bb', 893),
('schemas/integrations/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('schemas/integrations/models.py', '4f234d4672fa4afdf7330d0b77237186e715db81c4b60b0a3339e6b96b91d8c2', 776),
('schemas/leads/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('schemas/properties/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 0),
('schemas/properties/models.py', '57aa4df296d132e72d8962d1bdbf4686a857683dbbf762e739159665dc6ff0de', 2934),
('scripts/development/demo-lead.ps1', '9a07ee9a483c483d1cd434eccbf09c3810048c0288ef479b96616df0f4eada43', 687),
('scripts/development/run-api.ps1', 'b14200e767b2c0c5c41184f5e1df541d4d22245ac69b2184810552e04430d135', 250);

DO $preflight$
DECLARE
    v_project UUID;
BEGIN
    SELECT id INTO STRICT v_project
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF (SELECT COUNT(*) FROM step434_batch) <> 10 THEN
        RAISE EXCEPTION 'Invalid batch count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM step434_batch b
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
FROM step434_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id, source_path, content_sha256,
    size_bytes, source_reference_id
)
SELECT
    p.id, b.source_path, b.content_sha256, b.size_bytes, r.id
FROM step434_batch b
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
FROM step434_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_current_state (
    project_id, source_path, current_sha256
)
SELECT p.id, b.source_path, b.content_sha256
FROM step434_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

DO $verify$
DECLARE
    v_valid BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 451
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 451
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 451
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 451
    THEN
        RAISE EXCEPTION 'Unexpected test counts';
    END IF;

    SELECT COUNT(*) INTO v_valid
    FROM step434_batch b
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
    ) <> 126
    THEN
        RAISE EXCEPTION 'Unexpected event types';
    END IF;

    RAISE NOTICE 'PASS: All ten thirteenth-batch registrations validated';
    RAISE NOTICE 'PASS: Four-table integrity and history verified';
END
$verify$;

COMMIT;