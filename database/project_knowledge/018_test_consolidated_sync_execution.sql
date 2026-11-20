-- Step 350: consolidated writer integration test.
-- TEST DATABASE ONLY.

BEGIN;

DO $test$
DECLARE
    v_project_id UUID;
    v_new_hash TEXT := repeat('d', 64);
    v_original_hash TEXT :=
        'a519d7de67d9c23324ff2415194b20955a968e103ef959261b2c906d471193e5';
    v_current_hash TEXT :=
        'fa3456bd03a9f62497e084c8d4f94298956d71ed66af96602c0c79af572f190c';
    v_event_id BIGINT;
    v_caught BOOLEAN;
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 3
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 5
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 7
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected Step 350 baseline';
    END IF;

    SELECT id INTO STRICT v_project_id
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai';

    IF (
        SELECT current_sha256
        FROM project_knowledge.source_current_state
        WHERE project_id = v_project_id
          AND source_path = 'core/example.py'
    ) IS DISTINCT FROM v_current_hash THEN
        RAISE EXCEPTION 'Unexpected initial fingerprint';
    END IF;

    -- Test 1: register a new synthetic source.
    SELECT project_knowledge.sync_source_test(
        'dubai-real-estate-ai',
        'core/step349_new_file.py',
        NULL,
        v_new_hash,
        32
    ) INTO v_event_id;

    IF v_event_id IS NULL THEN
        RAISE EXCEPTION 'New-file registration returned no event';
    END IF;

    RAISE NOTICE 'PASS: New source registered';

    -- Test 2: return existing source to a historical fingerprint.
    SELECT project_knowledge.sync_source_test(
        'dubai-real-estate-ai',
        'core/example.py',
        v_current_hash,
        v_original_hash,
        26
    ) INTO v_event_id;

    IF v_event_id IS NULL THEN
        RAISE EXCEPTION 'Historical fingerprint change failed';
    END IF;

    RAISE NOTICE 'PASS: Historical fingerprint restored';

    -- Test 3: change back to the Step 343 fingerprint.
    SELECT project_knowledge.sync_source_test(
        'dubai-real-estate-ai',
        'core/example.py',
        v_original_hash,
        v_current_hash,
        31
    ) INTO v_event_id;

    IF v_event_id IS NULL THEN
        RAISE EXCEPTION 'Return transition failed';
    END IF;

    RAISE NOTICE 'PASS: Repeated fingerprint transition recorded';

    -- Test 4: stale update must fail.
    v_caught := FALSE;

    BEGIN
        PERFORM project_knowledge.sync_source_test(
            'dubai-real-estate-ai',
            'core/example.py',
            v_original_hash,
            repeat('e', 64),
            20
        );
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'Source baseline mismatch%' THEN
            v_caught := TRUE;
        ELSE
            RAISE;
        END IF;
    END;

    IF NOT v_caught THEN
        RAISE EXCEPTION 'Stale update was unexpectedly accepted';
    END IF;

    RAISE NOTICE 'PASS: Stale update rejected';

    -- Test 5: identical current fingerprint must fail.
    v_caught := FALSE;

    BEGIN
        PERFORM project_knowledge.sync_source_test(
            'dubai-real-estate-ai',
            'core/example.py',
            v_current_hash,
            v_current_hash,
            31
        );
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'No source change%' THEN
            v_caught := TRUE;
        ELSE
            RAISE;
        END IF;
    END;

    IF NOT v_caught THEN
        RAISE EXCEPTION 'No-change update was unexpectedly accepted';
    END IF;

    RAISE NOTICE 'PASS: No-change update rejected';

    -- Verify all four tables and final current state.
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 4
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 6
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 10
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 4
    THEN
        RAISE EXCEPTION 'Unexpected final table counts';
    END IF;

    IF (
        SELECT current_sha256
        FROM project_knowledge.source_current_state
        WHERE project_id = v_project_id
          AND source_path = 'core/example.py'
    ) IS DISTINCT FROM v_current_hash THEN
        RAISE EXCEPTION 'Final existing-file state mismatch';
    END IF;

    IF (
        SELECT current_sha256
        FROM project_knowledge.source_current_state
        WHERE project_id = v_project_id
          AND source_path = 'core/step349_new_file.py'
    ) IS DISTINCT FROM v_new_hash THEN
        RAISE EXCEPTION 'Final new-file state mismatch';
    END IF;

    RAISE NOTICE 'PASS: All final state checks passed';
END
$test$;

COMMIT;
