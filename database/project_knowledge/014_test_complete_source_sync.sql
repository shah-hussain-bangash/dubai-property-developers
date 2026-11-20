-- Step 343: complete existing-file synchronization.
-- TEST DATABASE ONLY.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*)
        FROM project_knowledge.source_change_events) <> 5
       OR (SELECT COUNT(*)
        FROM project_knowledge.source_versions) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected test baseline';
    END IF;
END
$preflight$;

CREATE FUNCTION project_knowledge.apply_complete_source_change_test(
    p_project_key TEXT,
    p_source_path TEXT,
    p_expected_hash TEXT,
    p_new_hash TEXT,
    p_size_bytes BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    v_project_id UUID;
    v_current_hash TEXT;
    v_reference_id UUID;
    v_event_id BIGINT;
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe target database';
    END IF;

    IF p_project_key <> 'dubai-real-estate-ai'
       OR p_source_path <> 'core/example.py'
    THEN
        RAISE EXCEPTION 'Unexpected synthetic source';
    END IF;

    IF p_expected_hash IS NULL
       OR p_expected_hash !~ '^[0-9a-f]{64}$'
       OR p_new_hash IS NULL
       OR p_new_hash !~ '^[0-9a-f]{64}$'
       OR p_size_bytes IS NULL
       OR p_size_bytes < 0
       OR p_size_bytes > 2000000
    THEN
        RAISE EXCEPTION 'Invalid source metadata';
    END IF;

    SELECT id INTO STRICT v_project_id
    FROM project_knowledge.projects
    WHERE project_key = p_project_key;

    SELECT current_sha256
    INTO v_current_hash
    FROM project_knowledge.source_current_state
    WHERE project_id = v_project_id
      AND source_path = p_source_path
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Source current state not found';
    END IF;

    IF v_current_hash <> p_expected_hash THEN
        RAISE EXCEPTION
            'Source baseline mismatch for %', p_source_path;
    END IF;

    IF v_current_hash = p_new_hash THEN
        RAISE EXCEPTION 'No source change';
    END IF;

    SELECT id INTO STRICT v_reference_id
    FROM project_knowledge.source_references
    WHERE project_id = v_project_id
      AND reference_key = 'source:' || p_source_path;

    INSERT INTO project_knowledge.source_versions (
        project_id, source_path, content_sha256,
        size_bytes, source_reference_id
    )
    VALUES (
        v_project_id, p_source_path, p_new_hash,
        p_size_bytes, v_reference_id
    )
    ON CONFLICT (project_id, source_path, content_sha256)
    DO NOTHING;

    INSERT INTO project_knowledge.source_change_events (
        project_id, source_path,
        previous_sha256, current_sha256, event_type
    )
    VALUES (
        v_project_id, p_source_path,
        v_current_hash, p_new_hash, 'modified'
    )
    RETURNING event_id INTO v_event_id;

    UPDATE project_knowledge.source_current_state
    SET current_sha256 = p_new_hash,
        updated_at = now()
    WHERE project_id = v_project_id
      AND source_path = p_source_path;

    RETURN v_event_id;
END;
$function$;

COMMIT;
