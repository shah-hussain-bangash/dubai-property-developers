-- Step 328: Source version history.
-- Only modifies project_knowledge.
-- Does not alter public.alembic_version.

BEGIN;

CREATE TABLE project_knowledge.source_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),

    source_path TEXT NOT NULL,

    content_sha256 TEXT NOT NULL,

    size_bytes BIGINT,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    source_reference_id UUID
        REFERENCES project_knowledge.source_references(id),

    CONSTRAINT source_versions_valid_hash
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT source_versions_valid_size
        CHECK (size_bytes IS NULL OR size_bytes >= 0),

    CONSTRAINT source_versions_nonblank_path
        CHECK (length(trim(source_path)) > 0),

    UNIQUE (project_id, source_path, content_sha256)
);

CREATE INDEX ix_source_versions_project_path
    ON project_knowledge.source_versions
    (project_id, source_path, recorded_at DESC);

-- Seed the initial version history from the existing inventory.

INSERT INTO project_knowledge.source_versions
    (
        project_id,
        source_path,
        content_sha256,
        size_bytes,
        source_reference_id
    )
SELECT
    s.project_id,
    s.source_path,
    s.content_sha256,
    CASE
        WHEN s.description ~ '[0-9]+ bytes'
        THEN substring(
            s.description FROM '([0-9]+) bytes'
        )::bigint
        ELSE NULL
    END,
    s.id
FROM project_knowledge.source_references AS s
JOIN project_knowledge.projects AS p
    ON p.id = s.project_id
WHERE p.project_key = 'dubai-real-estate-ai'
  AND s.reference_type = 'source_file'
ON CONFLICT (project_id, source_path, content_sha256)
DO NOTHING;

-- Verify the expected initial snapshot.

DO $verify_versions$
DECLARE
    source_count integer;
    version_count integer;
BEGIN
    SELECT COUNT(*) INTO source_count
    FROM project_knowledge.source_references
    WHERE reference_type = 'source_file';

    SELECT COUNT(*) INTO version_count
    FROM project_knowledge.source_versions;

    IF source_count <> 325 OR version_count <> 325 THEN
        RAISE EXCEPTION
            'Expected 325 sources and 325 versions; found % and %',
            source_count, version_count;
    END IF;
END
$verify_versions$;

COMMIT;
