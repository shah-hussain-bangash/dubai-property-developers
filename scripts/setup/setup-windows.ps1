# Local Windows setup. Run from a checkout with its reviewed npm lockfile.
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")

if (-not (Test-Path ".venv")) {
    $pythonArgs = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonCommand = "py"
        $pythonArgs = @("-3")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonCommand = "python"
    } else {
        throw "Python 3.12+ not found. Install it and re-run setup."
    }
    & $pythonCommand @pythonArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 or newer is required." }
    & $pythonCommand @pythonArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}

$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "The existing .venv needs Python 3.12 or newer." }
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $venvPy -m pip install -e ".[dev,documents]"
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (local development values only)."
}

if ((Get-Command npm.cmd -ErrorAction SilentlyContinue) -and (Get-Command node -ErrorAction SilentlyContinue)) {
    node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit(major>22 || (major===22 && minor>=12) ? 0 : 1)"
    if ($LASTEXITCODE -ne 0) { throw "Node.js 22.12+ is required for the dashboard." }
    Push-Location "apps/dashboard"
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "Dashboard lockfile installation failed." }
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "Node.js/npm not found - dashboard installation skipped. Install Node.js 22.12+ and run npm ci in apps/dashboard."
}

Write-Host "Setup complete. Run tests: .\.venv\Scripts\python -m pytest"
