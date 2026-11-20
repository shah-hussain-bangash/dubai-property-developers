# Windows local setup: creates .venv, installs backend deps, prepares .env and dashboard deps.
# Usage (from repo root): powershell -ExecutionPolicy Bypass -File scripts/setup/setup-windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv .venv
    } else {
        throw "Python 3.12+ not found. Install from https://www.python.org/downloads/ and re-run."
    }
}
$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -e ".[dev,documents]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (local development values only)."
}

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location "apps/dashboard"
    npm install
    Pop-Location
} else {
    Write-Warning "Node.js/npm not found - skipping dashboard install. Install Node.js 20 LTS."
}

Write-Host "Setup complete. Run tests: .\.venv\Scripts\python -m pytest"
