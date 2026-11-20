-- Step 331: controlled incremental source synchronization
-- Contains fingerprints and file metadata, not source contents.
-- Do not execute without reviewing the change report.
-- Original source references and earlier versions are preserved.

BEGIN;

DO $verify_source_baseline$
DECLARE
    item jsonb;
    latest_hash text;
BEGIN
    FOR item IN
        SELECT value
        FROM jsonb_array_elements(
            $source_sync_payload$[{"source_path":"core/new_module.py","sha256":"a563d1b65048464a650a5227dffbe369eaa96e738a866e266d154c49c3d902a7","size_bytes":23,"previous_sha256":null},{"source_path":"core/example.py","sha256":"be37dd9a884e425f3bf02a40f7fa2e1961fc349870941cc358830ed2b695333a","size_bytes":25,"previous_sha256":"a519d7de67d9c23324ff2415194b20955a968e103ef959261b2c906d471193e5"}]$source_sync_payload$::jsonb
        )
    LOOP
        SELECT v.content_sha256 INTO latest_hash
        FROM project_knowledge.source_versions AS v
        JOIN project_knowledge.projects AS p
            ON p.id = v.project_id
        WHERE p.project_key = 'dubai-real-estate-ai'
          AND v.source_path = item->>'source_path'
        ORDER BY v.recorded_at DESC, v.id DESC
        LIMIT 1;

        IF latest_hash IS DISTINCT FROM
           (item->>'previous_sha256') THEN
            RAISE EXCEPTION
                'Source baseline mismatch for %',
                item->>'source_path';
        END IF;
    END LOOP;
END
$verify_source_baseline$;

INSERT INTO project_knowledge.source_references
    (
        project_id, reference_key, reference_type,
        source_path, description, content_sha256
    )
SELECT
    p.id,
    'source:' || (item->>'source_path'),
    'source_file',
    item->>'source_path',
    '.source file; ' || (item->>'size_bytes') || ' bytes',
    item->>'sha256'
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_array_elements(
    $source_sync_payload$[{"source_path":"core/new_module.py","sha256":"a563d1b65048464a650a5227dffbe369eaa96e738a866e266d154c49c3d902a7","size_bytes":23,"previous_sha256":null},{"source_path":"core/example.py","sha256":"be37dd9a884e425f3bf02a40f7fa2e1961fc349870941cc358830ed2b695333a","size_bytes":25,"previous_sha256":"a519d7de67d9c23324ff2415194b20955a968e103ef959261b2c906d471193e5"}]$source_sync_payload$::jsonb
) AS item
WHERE p.project_key = 'dubai-real-estate-ai'
  AND item->>'previous_sha256' IS NULL
ON CONFLICT (project_id, reference_key) DO NOTHING;

INSERT INTO project_knowledge.source_versions
    (
        project_id, source_path, content_sha256,
        size_bytes, source_reference_id
    )
SELECT
    p.id,
    item->>'source_path',
    item->>'sha256',
    (item->>'size_bytes')::bigint,
    s.id
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_array_elements(
    $source_sync_payload$[{"source_path":"core/new_module.py","sha256":"a563d1b65048464a650a5227dffbe369eaa96e738a866e266d154c49c3d902a7","size_bytes":23,"previous_sha256":null},{"source_path":"core/example.py","sha256":"be37dd9a884e425f3bf02a40f7fa2e1961fc349870941cc358830ed2b695333a","size_bytes":25,"previous_sha256":"a519d7de67d9c23324ff2415194b20955a968e103ef959261b2c906d471193e5"}]$source_sync_payload$::jsonb
) AS item
LEFT JOIN project_knowledge.source_references AS s
    ON s.project_id = p.id
   AND s.reference_key = 'source:' || (item->>'source_path')
WHERE p.project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, source_path, content_sha256)
DO NOTHING;

COMMIT;
