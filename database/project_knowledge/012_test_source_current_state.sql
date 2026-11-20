-- Step 339: current-source-state experiment.
-- TEST DATABASE ONLY.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 3
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected test history';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'project_knowledge'
          AND table_name = 'source_current_state'
    ) THEN
        RAISE EXCEPTION 'Current-state table already exists';
    END IF;
END
$preflight$;

CREATE TABLE project_knowledge.source_current_state (
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),

    source_path TEXT NOT NULL,

    current_sha256 TEXT NOT NULL,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (project_id, source_path),

    CONSTRAINT current_state_valid_hash
        CHECK (current_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT current_state_nonblank_path
        CHECK (length(trim(source_path)) > 0)
);

-- core/example.py: the last synthetic event returned to A.
INSERT INTO project_knowledge.source_current_state
    (project_id, source_path, current_sha256)
SELECT
    p.id,
    'core/example.py',
    e.current_sha256
FROM project_knowledge.projects AS p
CROSS JOIN LATERAL (
    SELECT current_sha256
    FROM project_knowledge.source_change_events
    WHERE project_id = p.id
      AND source_path = 'core/example.py'
    ORDER BY event_id DESC
    LIMIT 1
) AS e
WHERE p.project_key = 'dubai-real-estate-ai';

-- core/new_module.py: its only recorded content version.
INSERT INTO project_knowledge.source_current_state
    (project_id, source_path, current_sha256)
SELECT
    project_id,
    source_path,
    content_sha256
FROM project_knowledge.source_versions
WHERE source_path = 'core/new_module.py';

DO $verify_state$
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 2
    THEN
        RAISE EXCEPTION 'Expected exactly two current-state records';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM project_knowledge.source_current_state AS s
        JOIN project_knowledge.source_change_events AS e
          ON e.project_id = s.project_id
         AND e.source_path = s.source_path
        WHERE s.source_path = 'core/example.py'
          AND e.event_id = (
              SELECT MAX(event_id)
              FROM project_knowledge.source_change_events
          )
          AND s.current_sha256 = e.current_sha256
    ) THEN
        RAISE EXCEPTION 'Latest event and current state differ';
    END IF;
END
$verify_state$;

COMMIT;
