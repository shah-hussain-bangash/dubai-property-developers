-- Project Knowledge Schema v1
-- Isolated from existing public application tables.
-- This migration does not modify public.alembic_version.

CREATE SCHEMA IF NOT EXISTS project_knowledge;

CREATE TABLE project_knowledge.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_key TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT project_key_not_blank
        CHECK (length(trim(project_key)) > 0)
);

CREATE TABLE project_knowledge.knowledge_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),
    entry_key TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'documented',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    source_reference TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, entry_key),
    CONSTRAINT valid_knowledge_verification
        CHECK (verification_status IN (
            'verified', 'unverified', 'historical', 'superseded'
        ))
);

CREATE TABLE project_knowledge.development_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),
    step_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    description TEXT,
    evidence_reference TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, step_number),
    CONSTRAINT valid_milestone_status
        CHECK (status IN (
            'pending', 'in_progress', 'completed',
            'blocked', 'superseded'
        ))
);

CREATE TABLE project_knowledge.test_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),
    run_key TEXT NOT NULL,
    suite_name TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    result TEXT NOT NULL,
    evidence_reference TEXT,
    executed_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, run_key),
    CONSTRAINT nonnegative_test_counts
        CHECK (
            passed >= 0 AND failed >= 0
            AND skipped >= 0 AND warning_count >= 0
        )
);

CREATE TABLE project_knowledge.source_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),
    reference_key TEXT NOT NULL,
    reference_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    description TEXT,
    content_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, reference_key)
);

CREATE TABLE project_knowledge.development_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES project_knowledge.projects(id),
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_reference TEXT,
    occurred_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, event_key)
);

CREATE INDEX ix_knowledge_entries_project_category
    ON project_knowledge.knowledge_entries
    (project_id, category);

CREATE INDEX ix_knowledge_entries_metadata
    ON project_knowledge.knowledge_entries
    USING GIN (metadata);

CREATE INDEX ix_milestones_project_step
    ON project_knowledge.development_milestones
    (project_id, step_number);

CREATE INDEX ix_development_events_project_time
    ON project_knowledge.development_events
    (project_id, occurred_at DESC);

CREATE INDEX ix_test_runs_project_time
    ON project_knowledge.test_runs
    (project_id, executed_at DESC);
