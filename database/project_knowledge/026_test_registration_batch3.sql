
-- Step 378: second batch, rollback-only.
BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 345
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 345
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 345
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 345
    THEN
        RAISE EXCEPTION 'Unexpected Step 378 baseline';
    END IF;
END
$guard$;

CREATE TEMP TABLE step378_batch (
    source_path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO step378_batch VALUES
('apps/dashboard/.eslintrc.json', '0cbbcf3b2a10330bbfbbdccd658ce2cb965f61cb008dbd11a7f60e0ad9654b94', 58),
('apps/dashboard/package.json', '97c962f619e79a8851394280cbb8f0e9beb94896a3d2ec1eba5e5b6c23fc2743', 925),
('apps/dashboard/src/app/globals.css', '3263a23154203e89532dd2fc9f4edc4c0b8fd0be3ba4684a0cc8220163a5efcc', 9020),
('apps/dashboard/src/app/login/login.module.css', '83bb4b4883591127b03b33341af3b71fbccdd173dfd87feb28d35dce4c4e8f13', 865),
('apps/dashboard/src/app/status-page.module.css', 'd1fedcdd49aa8ce29c2292afda1690e4ada1464d3c68d5632d96b336bf06b651', 560),
('apps/dashboard/src/components/charts/charts.module.css', '7d52fee202979c4f1f92e1052a5b29d38def67cd4947d7d6c6f9143988f296a6', 2542),
('apps/dashboard/src/components/layout/AppShell.module.css', '363e258717a007e0f59df3e224bc495d7903a369c6351282cfe1937e07bf61ac', 633),
('apps/dashboard/src/components/layout/BrandMark.module.css', '1f3149932c4fa9aa65fddcc21b3c2cb88b3584bd87cd6555184159e3cd9d3a34', 445),
('apps/dashboard/src/components/layout/Sidebar.module.css', '3e38bed7b970ad52aef6c7a308930a739515400dae5ab76f236f94a61bf3b825', 2985),
('apps/dashboard/src/components/layout/TopBar.module.css', '0ce949dab046b402dc943b6cf4b14c771777b90bff2aecaae20fe784195cef2e', 1991);

DO $preflight$
DECLARE
    v_project UUID;
BEGIN
    SELECT id INTO STRICT v_project
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF (SELECT COUNT(*) FROM step378_batch) <> 10 THEN
        RAISE EXCEPTION 'Invalid batch count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM step378_batch b
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
    b.source_path, 'Step 378 rollback-only test',
    b.content_sha256
FROM step378_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id, source_path, content_sha256,
    size_bytes, source_reference_id
)
SELECT
    p.id, b.source_path, b.content_sha256, b.size_bytes, r.id
FROM step378_batch b
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
FROM step378_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_current_state (
    project_id, source_path, current_sha256
)
SELECT p.id, b.source_path, b.content_sha256
FROM step378_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

DO $verify$
DECLARE
    v_valid BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 355
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 355
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 355
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 355
    THEN
        RAISE EXCEPTION 'Unexpected test counts';
    END IF;

    SELECT COUNT(*) INTO v_valid
    FROM step378_batch b
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
    ) <> 30
    THEN
        RAISE EXCEPTION 'Unexpected event types';
    END IF;

    RAISE NOTICE 'PASS: All ten second-batch registrations validated';
    RAISE NOTICE 'PASS: Four-table integrity and history verified';
END
$verify$;

ROLLBACK;
