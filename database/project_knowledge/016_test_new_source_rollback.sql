-- Step 347: transactional rollback across four tables.
-- Execute ONLY in dubai_ai_knowledge_sync_test.

BEGIN;

DO $test$
DECLARE
    v_project_id UUID;
    v_reference_id UUID;
    v_event_id BIGINT;
    v_path TEXT := 'core/step347_rollback_probe.py';
    v_hash TEXT := repeat('c', 64);
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 3
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 5
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 7
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected Step 347 baseline';
    END IF;

    SELECT id INTO STRICT v_project_id
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF EXISTS (
        SELECT 1 FROM project_knowledge.source_references
        WHERE project_id = v_project_id AND source_path = v_path
    )
    OR EXISTS (
        SELECT 1 FROM project_knowledge.source_versions
        WHERE project_id = v_project_id AND source_path = v_path
    )
    OR EXISTS (
        SELECT 1 FROM project_knowledge.source_change_events
        WHERE project_id = v_project_id AND source_path = v_path
    )
    OR EXISTS (
        SELECT 1 FROM project_knowledge.source_current_state
        WHERE project_id = v_project_id AND source_path = v_path
    )
    THEN
        RAISE EXCEPTION 'Step 347 probe already exists';
    END IF;

    INSERT INTO project_knowledge.source_references (
        project_id, reference_key, reference_type,
        source_path, description, content_sha256
    )
    VALUES (
        v_project_id,
        'source:' || v_path,
        'source_file',
        v_path,
        'Step 347 rollback-only synthetic source',
        v_hash
    )
    RETURNING id INTO v_reference_id;

    INSERT INTO project_knowledge.source_versions (
        project_id, source_path, content_sha256,
        size_bytes, source_reference_id
    )
    VALUES (
        v_project_id, v_path, v_hash, 25, v_reference_id
    );

    INSERT INTO project_knowledge.source_change_events (
        project_id, source_path, previous_sha256,
        current_sha256, event_type
    )
    VALUES (
        v_project_id, v_path, NULL, v_hash, 'added'
    )
    RETURNING event_id INTO v_event_id;

    INSERT INTO project_knowledge.source_current_state (
        project_id, source_path, current_sha256
    )
    VALUES (
        v_project_id, v_path, v_hash
    );

    -- Confirm every insert was visible within this transaction.
    IF NOT EXISTS (
        SELECT 1 FROM project_knowledge.source_references
        WHERE id = v_reference_id
    )
    OR NOT EXISTS (
        SELECT 1 FROM project_knowledge.source_versions
        WHERE project_id = v_project_id AND source_path = v_path
    )
    OR NOT EXISTS (
        SELECT 1 FROM project_knowledge.source_change_events
        WHERE event_id = v_event_id
    )
    OR NOT EXISTS (
        SELECT 1 FROM project_knowledge.source_current_state
        WHERE project_id = v_project_id AND source_path = v_path
    )
    THEN
        RAISE EXCEPTION 'Four-table insertion verification failed';
    END IF;

    -- This error intentionally aborts all four inserts.
    RAISE EXCEPTION 'STEP347_EXPECTED_ROLLBACK';
END
$test$;

COMMIT;
