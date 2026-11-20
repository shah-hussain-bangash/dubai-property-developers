-- Step 340: atomic current-state synchronization.
-- TEST DATABASE ONLY.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe target database';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM project_knowledge.source_current_state
    ) <> 2 THEN
        RAISE EXCEPTION 'Unexpected current-state baseline';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'project_knowledge'
          AND p.proname = 'apply_source_change_test'
    ) THEN
        RAISE EXCEPTION 'Test function already exists';
    END IF;
END
$preflight$;

CREATE FUNCTION project_knowledge.apply_source_change_test(
    p_project_key TEXT,
    p_source_path TEXT,
    p_expected_hash TEXT,
    p_new_hash TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    v_project_id UUID;
    v_current_hash TEXT;
    v_event_id BIGINT;
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF p_project_key <> 'dubai-real-estate-ai' THEN
        RAISE EXCEPTION 'Unexpected project key';
    END IF;

    IF p_source_path IS NULL
       OR p_source_path !~ '^core/[a-zA-Z0-9_]+[.]py$'
    THEN
        RAISE EXCEPTION 'Invalid synthetic source path';
    END IF;

    IF p_expected_hash IS NULL
       OR p_expected_hash !~ '^[0-9a-f]{64}$'
       OR p_new_hash IS NULL
       OR p_new_hash !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION 'Invalid source fingerprint';
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
            'Source baseline mismatch for %',
            p_source_path;
    END IF;

    IF v_current_hash = p_new_hash THEN
        RAISE EXCEPTION
            'No source change for %',
            p_source_path;
    END IF;

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
        v_current_hash,
        p_new_hash,
        'modified'
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
