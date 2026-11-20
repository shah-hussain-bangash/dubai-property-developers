-- Step 338: append-only source history experiment.
-- TEST DATABASE ONLY. Not approved for live database.

BEGIN;

DO $preflight$
BEGIN
    IF current_database() <> 'dubai_ai_knowledge_sync_test' THEN
        RAISE EXCEPTION 'Unsafe database target';
    END IF;

    IF (SELECT COUNT(*) FROM project_knowledge.source_references) <> 2
       OR (SELECT COUNT(*) FROM project_knowledge.source_versions) <> 3
    THEN
        RAISE EXCEPTION 'Unexpected test baseline';
    END IF;

    IF (SELECT COUNT(*)
        FROM project_knowledge.source_versions
        WHERE source_path = 'core/example.py') <> 2
    THEN
        RAISE EXCEPTION 'Original and modified versions not found';
    END IF;
END
$preflight$;

CREATE TABLE project_knowledge.source_change_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),

    source_path TEXT NOT NULL,

    previous_sha256 TEXT,
    current_sha256 TEXT NOT NULL,

    event_type TEXT NOT NULL,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_event_type
        CHECK (event_type IN ('initial', 'modified', 'added')),

    CONSTRAINT valid_current_hash
        CHECK (current_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT valid_previous_hash
        CHECK (
            previous_sha256 IS NULL OR
            previous_sha256 ~ '^[0-9a-f]{64}$'
        )
);

CREATE INDEX ix_source_change_events_project_path
    ON project_knowledge.source_change_events
    (project_id, source_path, event_id DESC);

-- Historical test observations: A, then B, then A again.
-- The final A represents a new event, not a new unique content hash.

WITH versions AS (
    SELECT
        p.id AS project_id,
        v.source_path,
        v.content_sha256,
        ROW_NUMBER() OVER (
            ORDER BY v.recorded_at, v.id
        ) AS version_number
    FROM project_knowledge.source_versions AS v
    JOIN project_knowledge.projects AS p
      ON p.id = v.project_id
    WHERE p.project_key = 'dubai-real-estate-ai'
      AND v.source_path = 'core/example.py'
),
fingerprints AS (
    SELECT
        project_id,
        source_path,
        MAX(content_sha256) FILTER (
            WHERE version_number = 1
        ) AS hash_a,
        MAX(content_sha256) FILTER (
            WHERE version_number = 2
        ) AS hash_b
    FROM versions
    GROUP BY project_id, source_path
)
INSERT INTO project_knowledge.source_change_events
    (
        project_id,
        source_path,
        previous_sha256,
        current_sha256,
        event_type
    )
SELECT
    f.project_id,
    f.source_path,
    CASE n.transition
        WHEN 1 THEN NULL
        WHEN 2 THEN f.hash_a
        WHEN 3 THEN f.hash_b
    END,
    CASE n.transition
        WHEN 1 THEN f.hash_a
        WHEN 2 THEN f.hash_b
        WHEN 3 THEN f.hash_a
    END,
    CASE n.transition
        WHEN 1 THEN 'initial'
        ELSE 'modified'
    END
FROM fingerprints AS f
CROSS JOIN generate_series(1, 3) AS n(transition)
WHERE f.hash_a IS NOT NULL
  AND f.hash_b IS NOT NULL
  AND f.hash_a <> f.hash_b
ORDER BY n.transition;

DO $verify_events$
DECLARE
    event_count integer;
    first_hash text;
    second_hash text;
    third_hash text;
BEGIN
    SELECT COUNT(*) INTO event_count
    FROM project_knowledge.source_change_events;

    IF event_count <> 3 THEN
        RAISE EXCEPTION 'Expected 3 history events; found %',
            event_count;
    END IF;

    SELECT current_sha256 INTO first_hash
    FROM project_knowledge.source_change_events
    ORDER BY event_id ASC LIMIT 1;

    SELECT current_sha256 INTO second_hash
    FROM project_knowledge.source_change_events
    ORDER BY event_id ASC OFFSET 1 LIMIT 1;

    SELECT current_sha256 INTO third_hash
    FROM project_knowledge.source_change_events
    ORDER BY event_id ASC OFFSET 2 LIMIT 1;

    IF first_hash <> third_hash OR first_hash = second_hash THEN
        RAISE EXCEPTION 'A-B-A transition verification failed';
    END IF;
END
$verify_events$;

COMMIT;
