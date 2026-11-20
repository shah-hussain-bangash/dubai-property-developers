
-- Step 368: temporary 10-file registration test.
-- All test inserts are rolled back.
BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_verify_20261019_095633' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 325
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 325
    THEN
        RAISE EXCEPTION 'Unexpected registration baseline';
    END IF;
END
$guard$;

CREATE TEMP TABLE step368_batch (
    source_path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO step368_batch VALUES
('integrations/base.py', '9683f3b3125389d13671271443825f4b75383cd5b448fa4f311478590067e37d', 4880),
('integrations/espocrm/client.py', '5a622ee57655dd900c0508d19709558ba37290b4a361c4bf5cea4ecdb2e67a8b', 5466),
('integrations/n8n/client.py', '57c74c73c284be5c7794fa25b631f3b4e42c8fd1cc0544883461fc4ea24b5bcb', 2127),
('integrations/propertyfinder/client.py', '3130494df1a2d6c76e882cf56f06b8a13b44a1d3c721c438eaf6c05777c491b6', 1045),
('knowledge/ingestion/pipeline.py', '678fcefc339b44b16637788b41a81b9c0194c1be8c7f321a6736c8f26925d594', 2136),
('knowledge/ingestion/chunking.py', 'a211dfb85513bdd540aa6c4fde87654d2a54f53301ec79e01cba9510d606f721', 1541),
('knowledge/retrieval/retriever.py', '91b83b008631a8395c2f185f2381171a2eba2471ae6e5ac587f90c9a03e8daf8', 1880),
('knowledge/vectorstores/pgvector.py', 'e35bb67cf4e5c9423a592a618d41c97bf75f62354e9b1d733ebb435f810fd0cf', 3938),
('schemas/leads/models.py', '26e1781222b6af4f68238b913da29ccffce5e2a1987e25448c495ee18f9609cf', 4444),
('tools/property/matching.py', '1b6efc673cc001958a1e084508c5379fcc2d93bf95694af4dda825ba520c615b', 4245);

DO $guard$
DECLARE
    v_project UUID;
BEGIN
    SELECT id INTO STRICT v_project
    FROM project_knowledge.projects
    WHERE project_key = 'dubai-real-estate-ai'
    FOR UPDATE;

    IF (SELECT COUNT(*) FROM step368_batch) <> 10 THEN
        RAISE EXCEPTION 'Invalid batch count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM step368_batch b
        WHERE EXISTS (
            SELECT 1 FROM project_knowledge.source_references r
            WHERE r.project_id = v_project AND r.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_versions v
            WHERE v.project_id = v_project AND v.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_current_state s
            WHERE s.project_id = v_project AND s.source_path = b.source_path
        )
        OR EXISTS (
            SELECT 1 FROM project_knowledge.source_change_events e
            WHERE e.project_id = v_project AND e.source_path = b.source_path
        )
    ) THEN
        RAISE EXCEPTION 'One or more batch files already registered';
    END IF;
END
$guard$;

INSERT INTO project_knowledge.source_references (
    project_id, reference_key, reference_type,
    source_path, description, content_sha256
)
SELECT
    p.id, 'source:' || b.source_path, 'source_file',
    b.source_path, 'Step 370 verified registration',
    b.content_sha256
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_versions (
    project_id, source_path, content_sha256,
    size_bytes, source_reference_id
)
SELECT p.id, b.source_path, b.content_sha256,
       b.size_bytes, r.id
FROM step368_batch b
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
SELECT p.id, b.source_path, NULL,
       b.content_sha256, 'added'
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

INSERT INTO project_knowledge.source_current_state (
    project_id, source_path, current_sha256
)
SELECT p.id, b.source_path, b.content_sha256
FROM step368_batch b
CROSS JOIN project_knowledge.projects p
WHERE p.project_key = 'dubai-real-estate-ai';

DO $verify$
DECLARE
    v_good BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 335
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 335
       OR (SELECT COUNT(*) FROM project_knowledge.source_change_events) <> 335
       OR (SELECT COUNT(*) FROM project_knowledge.source_current_state) <> 335
    THEN
        RAISE EXCEPTION 'Unexpected test counts';
    END IF;

    SELECT COUNT(*) INTO v_good
    FROM step368_batch b
    JOIN project_knowledge.source_references r
      ON r.source_path = b.source_path
     AND r.content_sha256 = b.content_sha256
    JOIN project_knowledge.source_versions v
      ON v.source_reference_id = r.id
     AND v.project_id = r.project_id
     AND v.source_path = b.source_path
     AND v.content_sha256 = b.content_sha256
     AND v.size_bytes = b.size_bytes
    JOIN project_knowledge.source_current_state s
      ON s.project_id = r.project_id
     AND s.source_path = b.source_path
     AND s.current_sha256 = b.content_sha256
    JOIN project_knowledge.source_change_events e
      ON e.project_id = r.project_id
     AND e.source_path = b.source_path
     AND e.current_sha256 = b.content_sha256
     AND e.previous_sha256 IS NULL
     AND e.event_type = 'added';

    IF v_good <> 10 THEN
        RAISE EXCEPTION 'Registration link/hash validation failed: %', v_good;
    END IF;

    RAISE NOTICE 'PASS: All ten registrations valid within transaction';
    RAISE NOTICE 'PASS: Four-table links and SHA-256 values verified';
END
$verify$;

-- Never commit this test batch.
COMMIT;
