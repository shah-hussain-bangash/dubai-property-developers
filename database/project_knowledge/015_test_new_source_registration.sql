-- Step 345: atomic registration of a new synthetic file.
-- TEST DATABASE ONLY.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 2
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 4
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 6
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 2
    THEN
        RAISE EXCEPTION 'Unexpected Step 345 baseline';
    END IF;
END
$preflight$;

CREATE FUNCTION project_knowledge.register_new_source_test(
    p_project_key TEXT,
    p_source_path TEXT,
    p_sha256 TEXT,
    p_size_bytes BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    v_project_id UUID;
    v_reference_id UUID;
    v_event_id BIGINT;
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF p_project_key IS DISTINCT FROM 'dubai-real-estate-ai'
       OR p_source_path IS DISTINCT FROM 'core/step345_new_file.py'
    THEN
        RAISE EXCEPTION 'Unexpected synthetic project or path';
    END IF;

    IF p_sha256 IS NULL
       OR p_sha256 !~ '^[0-9a-f]{64}$'
       OR p_size_bytes IS NULL
       OR p_size_bytes < 0
       OR p_size_bytes > 2000000
    THEN
        RAISE EXCEPTION 'Invalid source metadata';
    END IF;

    -- Serialize new-file registration attempts for this project.
    SELECT id INTO STRICT v_project_id
    FROM project_knowledge.projects
    WHERE project_key = p_project_key
    FOR UPDATE;

    IF EXISTS (
        SELECT 1
        FROM project_knowledge.source_current_state
        WHERE project_id = v_project_id
          AND source_path = p_source_path
    )
    OR EXISTS (
        SELECT 1
        FROM project_knowledge.source_references
        WHERE project_id = v_project_id
          AND source_path = p_source_path
    )
    OR EXISTS (
        SELECT 1
        FROM project_knowledge.source_versions
        WHERE project_id = v_project_id
          AND source_path = p_source_path
    )
    OR EXISTS (
        SELECT 1
        FROM project_knowledge.source_change_events
        WHERE project_id = v_project_id
          AND source_path = p_source_path
    )
    THEN
        RAISE EXCEPTION 'Source already registered: %', p_source_path;
    END IF;

    INSERT INTO project_knowledge.source_references (
        project_id,
        reference_key,
        reference_type,
        source_path,
        description,
        content_sha256
    )
    VALUES (
        v_project_id,
        'source:' || p_source_path,
        'source_file',
        p_source_path,
        'Step 345 synthetic new source',
        p_sha256
    )
    RETURNING id INTO v_reference_id;

    INSERT INTO project_knowledge.source_versions (
        project_id,
        source_path,
        content_sha256,
        size_bytes,
        source_reference_id
    )
    VALUES (
        v_project_id,
        p_source_path,
        p_sha256,
        p_size_bytes,
        v_reference_id
    );

    INSERT INTO project_knowledge.source_change_events (
        project_id,
        source_path,
        previous_sha256,
        current_sha256,
        event_type
    )
    VALUES (
        v_project_id,
        p_source_path,
        NULL,
        p_sha256,
        'added'
    )
    RETURNING event_id INTO v_event_id;

    INSERT INTO project_knowledge.source_current_state (
        project_id,
        source_path,
        current_sha256
    )
    VALUES (
        v_project_id,
        p_source_path,
        p_sha256
    );

    RETURN v_event_id;
END;
$function$;

COMMIT;
