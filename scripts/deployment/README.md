# Pinned AWS dashboard release

This operator-run helper prepares the dashboard release at commit `41d1374426af6a0c053def6fa7a1e654e7f16065`. It runs only as root on the existing Ubuntu host and fails if the expected private website, data volume or backend network differs. It contains no credentials or application records.

Default behavior and `--prepare` build a separate candidate with a copied data volume. They leave the existing website running. The source archive is pinned by commit and SHA-256; the AWS service-token gateway remains read-only. Build steps have memory and CPU limits.

Only `--activate` stops the old dashboard, verifies a consistent private backup, switches the website, and checks trusted HTTPS. Failed activation attempts restore the old container without deleting or restoring the data volume. `--rollback` restarts the retained old container while preserving current records. `--status` prints release state only.

Keep the browser terminal open while an operation runs. Private logs and backups stay under the root-only release directory. Application services, databases and Caddy are not upgraded by this helper. Successful command-line checks still require a browser sign-in check with the existing owner account.

Local verification: 14 deployment-helper tests, 15 AWS gateway tests, TypeScript, lint and the dashboard production build passed. Docker/server preparation and activation require operator execution; local tests do not claim a completed deployment.
