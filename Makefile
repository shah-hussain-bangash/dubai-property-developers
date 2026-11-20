# Developer shortcuts (GNU make; on Windows use scripts/development/*.ps1 or Git Bash).
.PHONY: install lint format typecheck test test-integration coverage migrate migrate-sql seed api worker dashboard-install dashboard up down audit

PY ?= python

install:
	$(PY) -m pip install -e ".[dev,documents]"

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

typecheck:
	$(PY) -m mypy agents core tools integrations schemas database knowledge workflows apps/api apps/worker

test:
	$(PY) -m pytest

test-integration:
	RUN_INTEGRATION_TESTS=1 $(PY) -m pytest -m integration

coverage:
	$(PY) -m pytest --cov --cov-report=term-missing --cov-report=xml

migrate:
	$(PY) -m alembic upgrade head

migrate-sql:
	$(PY) -m alembic upgrade head --sql

seed:
	$(PY) -m database.seeds.load_demo

api:
	$(PY) -m uvicorn apps.api.app.main:app --reload --port 8000

worker:
	$(PY) -m apps.worker.main

dashboard-install:
	cd apps/dashboard && npm install

up:
	docker compose up --build

down:
	docker compose down

audit:
	$(PY) -m pip_audit
