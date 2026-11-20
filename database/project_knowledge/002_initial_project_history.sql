-- Project Knowledge: Initial Verified History
-- Does not modify application tables or public.alembic_version.
-- Records supported milestones and project architecture.
-- Safe to rerun: ON CONFLICT DO NOTHING.

BEGIN;

INSERT INTO project_knowledge.knowledge_entries
    (project_id, entry_key, category, title, content,
     verification_status, source_reference, metadata)
SELECT
    id,
    'architecture-platform-v1',
    'architecture',
    'Platform technology architecture',
    'Windows-local Python 3.12 and FastAPI backend, React/TypeScript dashboard, PostgreSQL 16 with pgvector, Redis, Docker Compose API and worker services. Experimental tool-execution coordination is not connected to the active gateway.',
    'verified',
    'Development history and Docker inspection, October 2026',
    '{"components":["FastAPI","Python","React","PostgreSQL","pgvector","Redis","Docker"]}'::jsonb
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

INSERT INTO project_knowledge.knowledge_entries
    (project_id, entry_key, category, title, content,
     verification_status, source_reference, metadata)
SELECT
    id,
    'database-isolation-v1',
    'security',
    'Database isolation and migration safeguards',
    'Application database dubai_ai uses Alembic revision 0006_job_recovery_operations. Experimental database dubai_ai_test is separate and uses experimental migrations through 0008_tool_request_fingerprint. Do not apply experimental migrations to the application without a reviewed rollout.',
    'verified',
    'PostgreSQL inspection and experimental integration test history',
    '{"application_database":"dubai_ai","experimental_database":"dubai_ai_test","application_revision":"0006_job_recovery_operations"}'::jsonb
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

INSERT INTO project_knowledge.knowledge_entries
    (project_id, entry_key, category, title, content,
     verification_status, source_reference)
SELECT
    id,
    'ledger-safety-v1',
    'security',
    'Tool execution safety requirements',
    'Experimental execution ledger uses tenant-scoped idempotency claims and request fingerprints. In-progress and uncertain outcomes must not be automatically retried. External-provider reconciliation and authorization are required before implementing recovery.',
    'verified',
    'Steps 285-304 experimental test history'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

INSERT INTO project_knowledge.knowledge_entries
    (project_id, entry_key, category, title, content,
     verification_status, source_reference)
SELECT
    id,
    'reconciliation-report-v1',
    'implementation',
    'Read-only reconciliation reporting',
    'Experimental reporting function classifies in_progress and uncertain execution claims by investigation priority. It excludes sensitive owner tokens, request fingerprints, payloads and results. Administrative authorization and retrieval interfaces remain future work.',
    'verified',
    'Step 304 pytest output'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

INSERT INTO project_knowledge.knowledge_entries
    (project_id, entry_key, category, title, content,
     verification_status, source_reference)
SELECT
    id,
    'agent-system-scope-v1',
    'agents',
    'Multi-agent development scope',
    'Project development describes a 13-agent real estate AI platform. Individual agent names, responsibilities and deployment states must be verified against the source repository before definitive inventory is imported.',
    'historical',
    'Project development history'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

INSERT INTO project_knowledge.development_milestones
    (project_id, step_number, title, status,
     description, evidence_reference)
SELECT
    id,
    304,
    'Read-only reconciliation report completed',
    'completed',
    'Verified experimental regression suite: 58 tests passed, one warning.',
    'Step 304 pytest results'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, step_number) DO NOTHING;

INSERT INTO project_knowledge.development_milestones
    (project_id, step_number, title, status,
     description, evidence_reference)
SELECT
    id,
    305,
    'Reconciliation report validation tests',
    'pending',
    'Additional security and boundary tests were proposed but completion has not been verified.',
    'Step 305 instructions and latest available test output'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, step_number) DO NOTHING;

INSERT INTO project_knowledge.test_runs
    (project_id, run_key, suite_name, passed, failed,
     warning_count, result, evidence_reference)
SELECT
    id,
    'experimental-suite-step304',
    'Execution ledger and reconciliation experimental suite',
    58,
    0,
    1,
    'passed',
    'Step 304 pytest output: 58 passed, 1 warning'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, run_key) DO NOTHING;

INSERT INTO project_knowledge.development_events
    (project_id, event_key, event_type, summary,
     evidence_reference)
SELECT
    id,
    'knowledge-schema-installed-20261016',
    'database',
    'Project knowledge schema installed in application PostgreSQL database; six tables created and project registered.',
    'Step 313 PostgreSQL output'
FROM project_knowledge.projects
WHERE project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, event_key) DO NOTHING;

COMMIT;
