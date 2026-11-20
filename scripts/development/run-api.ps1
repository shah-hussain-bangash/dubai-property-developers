# Start the FastAPI backend with auto-reload on http://localhost:8000 (docs at /docs).
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
.\.venv\Scripts\python.exe -m uvicorn apps.api.app.main:app --reload --port 8000
