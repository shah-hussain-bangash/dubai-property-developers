# Phase 1 deployment and data compatibility review

Reviewed on 26 November 2026 at parent revision
`5aa1bf393e41554665d180770bd5a232ed964ca9`, plus this change in
[PR 87](https://github.com/shah-hussain-bangash/dubai-property-developers/pull/87).
No running server or existing business data was changed.

## Storage blocker and change

The dashboard Dockerfile selected a non-root user without preparing its default
portal data directory. Compose also omitted a persistent dashboard volume. Portal
storage, authentication and member modules use `/app/portal-data` by default. A
fresh non-root image therefore lacked a prepared writable location, and records
in a container's writable layer would not survive replacement.

The image now prepares that directory with nextjs ownership and mode 0700, and
declares its path explicitly. Compose mounts a dedicated portal-data named volume.
This is separate from supplied-source SQLite, PostgreSQL and Redis storage.

A new dashboard-container CI job builds the actual dashboard image and runs
`scripts/maintenance/check_dashboard_storage.cjs` in two successive network-disabled
containers. Both use the same newly created disposable volume. The first creates
a synthetic lock and private file using fsync/rename; the second verifies its data,
ownership and permissions survive container replacement. Cleanup removes only
that job-created volume. No web server or provider is started.

Local Docker engine access was unavailable: the Docker configuration and engine
pipe reported permission denied. Container execution is delegated to GitHub CI;
no local permission changes or deployment were attempted. The pre-change image
was inspected, not run locally. The container probe is an executable storage
regression check, not evidence of a before-fix browser journey.

## Local checks

- Compose validation passes with the example environment and a fresh empty Docker
  CLI configuration directory. This command does not require engine access.
- `node --check scripts/maintenance/check_dashboard_storage.cjs` passes.
- **95 focused tests and seven subtests pass**, covering configuration safeguards,
  approval snapshots/expiry/conflicts, agent-specific action keys, source-backed
  approvals, API ownership and all-agent restart/source-format behavior.
- One existing Starlette TestClient/httpx warning remains in that Python 3.14 run.

From the source root:

```text
python -m pytest tests/unit/test_core_config_and_security.py tests/unit/test_approval_store_snapshots.py tests/unit/test_approval_expiry_reads.py tests/unit/test_approval_create_conflicts.py tests/security/test_agent_action_isolation.py tests/security/test_source_bound_approvals.py tests/security/test_assigned_source_api_isolation.py tests/security/test_agent_source_format_journey.py -q -p no:cacheprovider --basetemp=../fresh-compatibility-review
node --check scripts/maintenance/check_dashboard_storage.cjs
docker compose --env-file .env.example config --quiet
```

Container reproduction, on an authorized Linux Docker host, is the exact
dashboard-container job in `.github/workflows/ci.yml`: build the image, create a
fresh volume, mount the probe read-only, run write then read in separate non-root
containers, and remove only that disposable volume.

## Knowledge backup and restoration rehearsal

A disposable local SQLite database contained four fictional sources across two
agents and two organizations, including staff-only and customer-approved material.
SQLite's backup API created a consistent backup. The original was then deliberately
changed by deleting one fictional source. A second backup operation restored the
backup into a separate database. Exact row comparison matched all four original
rows; the original remained at three rows. Staff previews, customer exclusion and
cross-agent/organization abstention still held on the restored store.

[Machine-readable result](phase1-knowledge-restore-local-2026-11-26.json).
This demonstrates a local source-store restore, not a production-volume restore
or a browser portal/PostgreSQL backup. To repeat, use only fresh temporary paths,
construct fictional AssignedSources records, call sqlite3.Connection.backup for
backup and restoration, then compare agent_sources rows and scoped answers. Never
overwrite the live source path for a rehearsal.

## Compatibility and remaining release dependencies

- Existing portal data is not automatically copied from an old container into the
  new volume. Before deployment, identify the actual path, stop writes, privately
  back it up and rehearse restoration. Existing bind mounts/volumes may need
  environment-specific ownership preparation; fresh-volume tests do not prove it.
- API/worker share supplied-source storage, but approvals, audit, replay cache and
  conversation memory remain process-local. Redis/PostgreSQL service availability
  alone does not switch these runtime stores to persistent implementations.
- Changed agent action keys require reconciliation of old pending/completed
  actions. Legacy SQL memory needs ownership review; no automatic migration is added.
- Review the private owner verifier before shared source-management access. Hosted
  revision, eligible synthetic operator access and the full hosted journey remain
  unconfirmed. No live provider validation is implied.
- Rollback needs a compatible previous image/configuration and a verified backup;
  preserve candidate data and avoid blind replay of previous send approvals.

[Deployment storage and rollback instructions](../deployment/docker.md#portal-and-knowledge-storage)
describe the preparation. All five initial Phase 1 review groups now have records;
full PR sign-off and environment acceptance remain release decisions. No merge,
deployment, existing-volume migration or outbound customer communication occurred.
