-- Step 349: consolidated source synchronization prototype.
-- TEST DATABASE ONLY.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 3
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 5
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 7
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected Step 349 baseline';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'project_knowledge'
          AND p.proname = 'sync_source_test'
    ) THEN
        RAISE EXCEPTION 'Consolidated function already exists';
    END IF;
END
$preflight$;

CREATE FUNCTION project_knowledge.sync_source_test(
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

    IF p_project_key IS DISTINCT FROM 'dubai-real-estate-ai'
       OR p_source_path IS NULL
       OR p_source_path NOT IN (
           'core/example.py',
           'core/step349_new_file.py'
       )
    THEN
        RAISE EXCEPTION 'Unexpected project or source path';
    END IF;

    IF p_expected_hash IS NOT NULL
       AND p_expected_hash !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION 'Invalid expected fingerprint';
    END IF;

    IF p_new_hash IS NULL
       OR p_new_hash !~ '^[0-9a-f]{64}$'
       OR p_size_bytes IS NULL
       OR p_size_bytes < 0
       OR p_size_bytes > 2000000
    THEN
        RAISE EXCEPTION 'Invalid new source metadata';
    END IF;

    -- All calls through this function lock the same project row.
    -- This provides serialization, although at project-wide scope.
    SELECT id INTO STRICT v_project_id
    FROM project_knowledge.projects
    WHERE project_key = p_project_key
    FOR UPDATE;

    SELECT current_sha256 INTO v_current_hash
    FROM project_knowledge.source_current_state
    WHERE project_id = v_project_id
      AND source_path = p_source_path
    FOR UPDATE;

    IF NOT FOUND THEN
        -- A missing current-state record is only valid for new files.
        IF p_expected_hash IS NOT NULL THEN
            RAISE EXCEPTION
                'Source missing; expected existing state: %',
                p_source_path;
        END IF;

        -- Detect inconsistent or previously registered metadata.
        IF EXISTS (
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
            RAISE EXCEPTION
                'Inconsistent existing source metadata: %',
                p_source_path;
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
            'Step 349 consolidated synchronization test',
            p_new_hash
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
            p_new_hash,
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
            p_new_hash,
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
            p_new_hash
        );

    ELSE
        -- Existing files require an exact expected fingerprint.
        IF p_expected_hash IS DISTINCT FROM v_current_hash THEN
            RAISE EXCEPTION
                'Source baseline mismatch for %',
                p_source_path;
        END IF;

        IF p_new_hash = v_current_hash THEN
            RAISE EXCEPTION 'No source change for %', p_source_path;
        END IF;

        SELECT id INTO STRICT v_reference_id
        FROM project_knowledge.source_references
        WHERE project_id = v_project_id
          AND reference_key = 'source:' || p_source_path
          AND source_path = p_source_path;

        -- A-B-A transitions reuse historical content versions.
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
            p_new_hash,
            p_size_bytes,
            v_reference_id
        )
        ON CONFLICT (project_id, source_path, content_sha256)
        DO NOTHING;

        -- Every accepted transition creates a fresh event.
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
    END IF;

    RETURN v_event_id;
END;
$function$;

COMMIT;
