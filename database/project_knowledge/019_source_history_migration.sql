-- Step 355: source-history schema and initial backfill.
-- Execute ONLY against the restored verification database first.
-- Initial events describe the migration baseline, not earlier transitions.

BEGIN;

DO $preflight$
DECLARE
    v_project_id UUID;
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target: %', current_database();
    END IF;

    IF to_regclass('project_knowledge.source_change_events') IS NOT NULL
       OR to_regclass('project_knowledge.source_current_state') IS NOT NULL
    THEN
        RAISE EXCEPTION 'Source-history tables already exist';
    END IF;

    SELECT id INTO STRICT v_project_id
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai';

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.knowledge_entries) <> 25
    THEN
        RAISE EXCEPTION 'Unexpected restored knowledge baseline';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM (
            SELECT project_id, source_path
            FROM project_knowledge.source_versions
            GROUP BY project_id, source_path
        ) AS unique_paths
    ) <> 325 THEN
        RAISE EXCEPTION 'Source paths are not uniquely represented';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM project_knowledge.source_versions AS v
        LEFT JOIN project_knowledge.source_references AS r
          ON r.id = v.source_reference_id
        WHERE v.project_id IS DISTINCT FROM v_project_id
           OR r.id IS NULL
           OR r.project_id IS DISTINCT FROM v.project_id
           OR r.source_path IS DISTINCT FROM v.source_path
           OR v.content_sha256 !~ '^[0-9a-f]{64}$'
    ) THEN
        RAISE EXCEPTION 'Source baseline contains inconsistent metadata';
    END IF;
END
$preflight$;

CREATE TABLE project_knowledge.source_change_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),

    source_path TEXT NOT NULL,

    previous_sha256 TEXT,
    current_sha256 TEXT NOT NULL,

    event_type TEXT NOT NULL,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT history_event_nonblank_path
        CHECK (length(trim(source_path)) > 0),

    CONSTRAINT history_event_type_valid
        CHECK (event_type IN ('initial', 'added', 'modified')),

    CONSTRAINT history_event_current_hash_valid
        CHECK (current_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT history_event_previous_hash_valid
        CHECK (
            previous_sha256 IS NULL
            OR previous_sha256 ~ '^[0-9a-f]{64}$'
        ),

    CONSTRAINT history_event_initial_previous_null
        CHECK (
            event_type NOT IN ('initial', 'added')
            OR previous_sha256 IS NULL
        ),

    CONSTRAINT history_event_modified_previous_required
        CHECK (
            event_type <> 'modified'
            OR previous_sha256 IS NOT NULL
        )
);

CREATE INDEX ix_source_change_events_project_path
    ON project_knowledge.source_change_events
    (project_id, source_path, event_id DESC);

CREATE TABLE project_knowledge.source_current_state (
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),

    source_path TEXT NOT NULL,

    current_sha256 TEXT NOT NULL,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (project_id, source_path),

    CONSTRAINT current_state_nonblank_path
        CHECK (length(trim(source_path)) > 0),

    CONSTRAINT current_state_valid_hash
        CHECK (current_sha256 ~ '^[0-9a-f]{64}$')
);

-- Record the initial state of every known source file.
INSERT INTO project_knowledge.source_change_events (
    project_id,
    source_path,
    previous_sha256,
    current_sha256,
    event_type
)
SELECT
    project_id,
    source_path,
    NULL,
    content_sha256,
    'initial'
FROM project_knowledge.source_versions
ORDER BY project_id, source_path;

-- Initialize the authoritative current-state table.
INSERT INTO project_knowledge.source_current_state (
    project_id,
    source_path,
    current_sha256
)
SELECT
    project_id,
    source_path,
    content_sha256
FROM project_knowledge.source_versions;

DO $verify$
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 325
    THEN
        RAISE EXCEPTION 'Incomplete initial source-history backfill';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM project_knowledge.source_versions AS v
        LEFT JOIN project_knowledge.source_current_state AS s
          ON s.project_id = v.project_id
         AND s.source_path = v.source_path
        WHERE s.current_sha256 IS DISTINCT FROM v.content_sha256
    ) THEN
        RAISE EXCEPTION 'Source current-state fingerprint mismatch';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM project_knowledge.source_change_events
        WHERE event_type <> 'initial'
           OR previous_sha256 IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Unexpected initial history event';
    END IF;

    IF (SELECT version_num FROM public.alembic_version)
       IS DISTINCT FROM '0006_job_recovery_operations'
    THEN
        RAISE EXCEPTION 'Application Alembic revision changed';
    END IF;
END
$verify$;

COMMIT;
