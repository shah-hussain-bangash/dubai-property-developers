# Pinned AWS dashboard release

This operator-run helper prepares the dashboard release at commit `41d1374426af6a0c053def6fa7a1e654e7f16065`. It runs only as root on the existing Ubuntu host and fails if the expected website, data volume or private backend network differs. It contains no credentials or application records.

Default behavior and `--prepare` build a separate candidate with a copied data volume. They leave the existing website running. The source archive is pinned by commit and SHA-256; the AWS service-token gateway remains read-only. Build steps have memory and CPU limits. The helper permits only fixed Docker/archive executables, uses argument lists without a shell, and restricts HTTP probes to the reviewed destinations and ports.

Only `--activate` stops the old dashboard, verifies a consistent private backup, switches the website, and checks trusted HTTPS. Failed activation attempts restore the old container without deleting or restoring the data volume. `--rollback` restarts the retained old container while preserving current records. `--status` prints release state only.

Keep the browser terminal open while an operation runs. Private logs and backups stay under the root-only release directory. Application services, databases and Caddy are not upgraded by this helper. Existing owner credentials remain private.

## Verification

The operator ran preparation and activation on 20 November 2026. The terminal reported that candidate checks, the storage copy, trusted HTTPS and protected routes passed; the existing data volume, owner configuration, API service, Caddy and other applications were preserved. The previous website was retained stopped for rollback.

The operator then demonstrated successful browser access to the admin overview with its API-online indicator. A clearly labelled synthetic website enquiry appeared in the admin inbox with the entered budget, and its Closed status persisted after refresh. No enquiry message was sent. These checks verify this release and enquiry flow; they do not establish full production readiness or enable unconfigured providers.

Local validation before deployment included 14 helper tests, 15 AWS gateway tests, TypeScript, lint and the dashboard production build. Repository tests now cover source extraction, unsafe archives, verified backups, fail-closed preflights, activation rollback, and command/probe target restrictions. They mock Docker and network operations and do not access the live server or real records.
