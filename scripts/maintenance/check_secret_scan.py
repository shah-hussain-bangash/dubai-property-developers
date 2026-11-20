"""Verify narrow scanner exceptions without using real credentials or external services."""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


def check(binary: Path, config: Path) -> None:
    binary, config = binary.resolve(strict=True), config.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="credential-scan-check-") as temporary:
        parent = Path(temporary)
        root = parent / "source"
        fixture = root / "apps/dashboard/src/__tests__/PortalSecurityViews.test.tsx"
        catalogue = root / "database/project_knowledge/047_commit_registration_batch13.sql"
        fixture.parent.mkdir(parents=True)
        catalogue.parent.mkdir(parents=True)
        current = "Fictional" + "Current-647"
        replacement = "Fictional" + "Replacement-647"
        fixture.write_text(
            f"const values = [['Current password','{current}'],"
            f"['New password','{replacement}']];\n",
            encoding="utf-8",
        )
        catalogue.write_text(
            "('scripts/development/run-api.ps1', "
            "'b14200e767b2c0c5c41184f5e1df541d4d22245ac69b2184810552e04430d135', 250);\n",
            encoding="utf-8",
        )

        def scan():
            report = parent / "findings.json"
            result = subprocess.run(  # noqa: S603 -- Explicit local binary; fixed scanner arguments.
                [
                    str(binary),
                    "dir",
                    ".",
                    "--config",
                    str(config),
                    "--redact=100",
                    "--no-banner",
                    "--report-format=json",
                    "--report-path",
                    str(report),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode not in {0, 1}:
                raise RuntimeError("Secret scanner could not complete its regression check")
            content = report.read_text(encoding="utf-8")
            return result, json.loads(content), content

        result, findings, _ = scan()
        if result.returncode != 0 or findings:
            raise AssertionError("Reviewed fictional values and checksums must be accepted")
        for path in [fixture, catalogue, root / "unlisted-source.ts"]:
            # Generated for this check only; never registered with any service.
            token = secrets.token_hex(32)
            original = path.read_text(encoding="utf-8") if path.exists() else ""
            try:
                path.write_text(original + f'const api_key = "{token}";\n', encoding="utf-8")
                result, findings, report = scan()
                if result.returncode != 1 or not findings:
                    raise AssertionError(
                        "A new credential must be detected even in an exception path"
                    )
                if token in report or token in result.stdout or token in result.stderr:
                    raise AssertionError("Scanner output must redact the generated credential")
            finally:
                path.write_text(original, encoding="utf-8")
    print(
        "Scanner checks passed: reviewed fixtures accepted; new credentials detected and redacted."
    )


if __name__ == "__main__":
    check(
        Path(sys.argv[1]),
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(__file__).resolve().parents[2] / ".gitleaks.toml",
    )
