# Credential scanning

The [credential-scan job](../../.github/workflows/ci.yml) checks the fetched Git history on pull requests and pushes to main. It uses Gitleaks 8.30.1, verifies the downloaded Linux archive against a fixed SHA-256 digest, and redacts detected values in logs and the downloadable JSON report.

A finding fails the job. The report is available under the run's **Artifacts** section for seven days, including after a scan failure when a report was produced. This is pattern-based detection, not a guarantee that a repository contains no secrets.

## Reviewed exceptions

[.gitleaks.toml](../../.gitleaks.toml) extends the default rules. Its exceptions apply only to the generic API-key rule and require both a matching path and an exact reviewed value:

- Two fictional password strings in `PortalSecurityViews.test.tsx`.
- Two source-file SHA-256 fingerprints stored in four historical SQL catalogue files.

No whole test directory, SQL directory, commit or history baseline is excluded. Other credentials in those files remain subject to scanning.

The workflow runs [check_secret_scan.py](../../scripts/maintenance/check_secret_scan.py) before scanning. This verifies that the reviewed fixtures are accepted and fresh synthetic credentials are still detected and redacted inside both exception paths and an unrelated file.

## Local check

Use the official scanner release and verify its archive checksum before running:

```text
gitleaks git . --log-opts=--all --config=.gitleaks.toml --redact=100 --no-banner
python scripts/maintenance/check_secret_scan.py /path/to/gitleaks
```

Use a full Git checkout for history coverage. Local checks scan Git content; they do not need account credentials or access to the running website.

## Updating the scanner

Update the fixed release URL and SHA-256 digest together after verifying the official release. Run the exception/redaction check and a full history scan, then review the GitHub results before merging. Do not add broad path exclusions to make a failing scan pass. If a real credential is detected, revoke or rotate it and investigate its history before considering any source cleanup.
