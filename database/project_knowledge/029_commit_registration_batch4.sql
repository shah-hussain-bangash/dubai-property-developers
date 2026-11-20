
-- Step 373: second batch, rollback-only.
BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 355
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 355
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 355
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 355
    THEN
        RAISE EXCEPTION 'Unexpected Step 382 baseline';
    END IF;
END
$guard$;

CREATE TEMP TABLE step382_batch (
    source_path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO step382_batch VALUES
('apps/dashboard/src/components/ui/DataTable.module.css', '8f7bed932b66ca5766b8e6e79dffc06d8d716c79a46fd1e8e7ed2f2e474eb3ff', 1291),
('apps/dashboard/src/components/ui/DemoDataBanner.module.css', '66bf306b8ee24372dd72f9ef48aa696e5d8c2f23ca59328c14d164329384229a', 645),
('apps/dashboard/src/components/ui/KpiCard.module.css', 'b044909c05d7a54b1f3ef5123e46c7612d016a3ab9170f801776d9664c74a5ee', 1121),
('apps/dashboard/src/components/ui/PageHeader.module.css', 'e8e14257ce65a6de098a2dfcef4ed01884160ea00617b36e678558fa41778e17', 607),
('apps/dashboard/src/components/ui/States.module.css', 'f2b98e1936cbb16ae9125f35499d29d87594262b0c55e0079025e4352246681b', 1780),
('apps/dashboard/src/components/ui/StatusBadge.module.css', 'd50caadb86cf0fd374723185879312adac918b17f5213dc85d293147138de43a', 1227),
('apps/dashboard/src/features/agents/agents.module.css', '987f8c548d666d7bc17b62185eaf951a8f7e834552af1a3be519f52891d19c0c', 1746),
('apps/dashboard/src/features/auth/LoginForm.module.css', 'fb426b1e54f78622fcd37bca4ff1e045c9d3ed206bd23baae7a2a146de4ab7b7', 405),
('apps/dashboard/src/features/conversations/conversations.module.css', 'c39de71115c625972c2f779d7f87690f95956950c83512e6a9eb9fd79492b4f5', 2854),
('apps/dashboard/src/features/integrations/integrations.module.css', '5d18dc73d4bc3b06c9194368e22781e12d15112059ee79961a7e4aa555a91174', 614);

DO $preflight$
DECLARE
    v_project UUID;
BEGIN
    SELECT id INTO STRICT v_project
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF (SELECT COUNT(*) FROM step382_batch) <> 10 THEN
        RAISE EXCEPTION 'Invalid batch count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM step382_batch b
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
    b.source_path, 'Step 383 verified P1 registration',
    b.content_sha256
FROM step382_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id, source_path, content_sha256,
    size_bytes, source_reference_id
)
SELECT
    p.id, b.source_path, b.content_sha256, b.size_bytes, r.id
FROM step382_batch b
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
FROM step382_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_current_state (
    project_id, source_path, current_sha256
)
SELECT p.id, b.source_path, b.content_sha256
FROM step382_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

DO $verify$
DECLARE
    v_valid BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 365
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 365
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 365
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 365
    THEN
        RAISE EXCEPTION 'Unexpected test counts';
    END IF;

    SELECT COUNT(*) INTO v_valid
    FROM step382_batch b
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
    ) <> 40
    THEN
        RAISE EXCEPTION 'Unexpected event types';
    END IF;

    RAISE NOTICE 'PASS: All ten fourth-batch registrations validated';
    RAISE NOTICE 'PASS: Four-table integrity and history verified';
END
$verify$;

COMMIT;
