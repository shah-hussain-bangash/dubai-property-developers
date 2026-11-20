# Run lint, type checks and tests. Pass -Coverage for a coverage report.
param([switch]$Coverage)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
$py = ".\.venv\Scripts\python.exe"
& $py -m ruff check .
& $py -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker
if ($Coverage) { & $py -m pytest --cov --cov-report=term-missing } else { & $py -m pytest }
