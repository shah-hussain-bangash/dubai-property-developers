# Windows local development guide

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | python.org installer. Enable the `py` launcher and "Add to PATH" |
| Node.js | 20 LTS | Dashboard only |
| Git | latest | |
| Docker Desktop | latest | Optional: Postgres/Redis/full stack. Requires WSL 2 |
| VS Code | latest | Recommended extensions are in `.vscode/extensions.json` |

> If the repository sits on a network share (UNC path such as `\\server\share\...`), create the
> virtual environment on a local drive or map the share to a drive letter first. Some tools (npm,
> venv activation scripts, file watchers) behave poorly on UNC paths.

## Setup

```powershell
cd dubai-real-estate-ai
powershell -ExecutionPolicy Bypass -File scripts/setup/setup-windows.ps1
```

This creates `.venv`, installs `.[dev,documents]` in editable mode, copies `.env.example` to `.env`,
and runs `npm install` for the dashboard when npm is available.

## Daily commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest                                   # all tests (integration tests auto-skip)
python -m ruff check .                             # lint
python -m uvicorn apps.api.app.main:app --reload   # API on :8000, docs on /docs
python scripts/maintenance/verify_structure.py     # layout + import check
cd apps/dashboard; npm run dev                     # dashboard on :3000
```

VS Code tasks (`Ctrl+Shift+P` → *Run Task*) and launch configurations (F5) are provided for the API,
the worker and pytest.

## Database (optional)

```powershell
docker compose up -d postgres redis
python -m alembic upgrade head
python -m database.seeds.load_demo        # fictional data; refuses to run outside dev/test
$env:RUN_INTEGRATION_TESTS="1"; python -m pytest -m integration
```

To preview the migration SQL without a database, run `python -m alembic upgrade head --sql`.

## Troubleshooting

- **`ModuleNotFoundError: core`**: the package isn't installed. Run `pip install -e .` from the repo
  root, or run pytest from the repo root (`pythonpath = ["."]` is configured).
- **Execution policy errors**: run the scripts with `powershell -ExecutionPolicy Bypass -File ...`.
- **Port in use**: change `--port` or stop the other service. Docker binds to 127.0.0.1 only.
