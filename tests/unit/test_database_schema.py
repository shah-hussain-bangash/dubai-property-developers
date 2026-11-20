"""Schema/migration consistency checks that need no running database."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import database.models  # noqa: F401
from database.base import Base

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_TABLES = {
    "organizations", "users", "roles", "user_roles", "leads", "contacts", "projects",
    "properties", "property_units", "payment_plans", "opportunities", "conversations",
    "messages", "ai_agents", "agent_executions", "workflow_executions", "tasks",
    "integration_connections", "external_sync_records", "approval_requests", "audit_logs",
    "knowledge_documents", "knowledge_chunks", "chunk_embeddings",
}


def test_models_define_all_required_tables() -> None:
    assert REQUIRED_TABLES <= set(Base.metadata.tables)


def test_tenant_tables_have_org_foreign_key() -> None:
    global_tables = {"organizations", "roles", "user_roles", "ai_agents", "chunk_embeddings"}
    for name, table in Base.metadata.tables.items():
        if name in global_tables:
            continue
        fks = {fk.target_fullname for fk in table.c.organization_id.foreign_keys}
        assert "organizations.id" in fks, name


def test_constraint_names_fit_postgres_limit() -> None:
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            assert constraint.name is None or len(str(constraint.name)) <= 63
        for index in table.indexes:
            assert len(str(index.name)) <= 63


def test_offline_migration_creates_every_model_table(capsys: pytest.CaptureFixture[str]) -> None:
    buffer = io.StringIO()
    cfg = Config(str(ROOT / "alembic.ini"), output_buffer=buffer)
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    command.upgrade(cfg, "head", sql=True)
    sql = buffer.getvalue() + capsys.readouterr().out
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table}" in sql, table
    assert "VECTOR(1536)" in sql.upper()
    assert "USING hnsw" in sql
