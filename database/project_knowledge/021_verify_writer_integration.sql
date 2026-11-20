-- Step 358: full writer integration with intentional rollback.
-- Restored verification database ONLY.

BEGIN;

DO $integration$
DECLARE
    v_a TEXT := repeat('a', 64);
    v_b TEXT := repeat('b', 64);
    v_event_id BIGINT;
    v_rejected BOOLEAN := FALSE;
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 325
    THEN
        RAISE EXCEPTION 'Unexpected restored baseline';
    END IF;

    -- Test 1: New-file registration (A).
    SELECT project_knowledge.sync_source_verify(
        'dubai-real-estate-ai',
        'core/step357_probe.py',
        NULL,
        v_a,
        20
    ) INTO v_event_id;

    IF v_event_id IS NULL THEN
        RAISE EXCEPTION 'New-file event missing';
    END IF;

    RAISE NOTICE 'PASS: New-file registration';

    -- Test 2: Modify A to B.
    SELECT project_knowledge.sync_source_verify(
        'dubai-real-estate-ai',
        'core/step357_probe.py',
        v_a,
        v_b,
        25
    ) INTO v_event_id;

    IF v_event_id IS NULL THEN
        RAISE EXCEPTION 'Modification event missing';
    END IF;

    RAISE NOTICE 'PASS: A to B modification';

    -- Test 3: Return B to A.
    SELECT project_knowledge.sync_source_verify(
        'dubai-real-estate-ai',
        'core/step357_probe.py',
        v_b,
        v_a,
        20
    ) INTO v_event_id;

    IF v_event_id IS NULL THEN
        RAISE EXCEPTION 'Historical transition missing';
    END IF;

    RAISE NOTICE 'PASS: B to A historical transition';

    -- Test 4: Reject stale update.
    BEGIN
        PERFORM project_knowledge.sync_source_verify(
            'dubai-real-estate-ai',
            'core/step357_probe.py',
            v_b,
            repeat('c', 64),
            30
        );
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'Source baseline mismatch%' THEN
            v_rejected := TRUE;
        ELSE
            RAISE;
        END IF;
    END;

    IF NOT v_rejected THEN
        RAISE EXCEPTION 'Stale update was accepted';
    END IF;

    RAISE NOTICE 'PASS: Stale update rejected';

    -- Test 5: Validate all four tables in this transaction.
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 326
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 327
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 328
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 326
    THEN
        RAISE EXCEPTION 'Unexpected integration test counts';
    END IF;

    IF (
        SELECT current_sha256
        FROM project_knowledge.source_current_state
        WHERE source_path = 'core/step357_probe.py'
    ) IS DISTINCT FROM v_a THEN
        RAISE EXCEPTION 'Final probe fingerprint mismatch';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM project_knowledge.source_change_events
        WHERE source_path = 'core/step357_probe.py'
    ) <> 3 THEN
        RAISE EXCEPTION 'Expected three history events';
    END IF;

    RAISE NOTICE 'PASS: Four-table consistency';
    RAISE NOTICE 'PASS: Integration checks completed';

    -- Intentionally prevent test data from being committed.
    RAISE EXCEPTION 'STEP358_EXPECTED_ROLLBACK';
END
$integration$;

COMMIT;
