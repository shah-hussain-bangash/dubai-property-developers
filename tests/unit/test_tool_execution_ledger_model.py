from __future__ import annotations

import uuid

from sqlalchemy import UniqueConstraint, Uuid

import database.models
from database.models.tool_execution import ToolExecutionLedger


def test_execution_ledger_table_name() -> None:
    assert ToolExecutionLedger.__tablename__ == "tool_execution_ledger"


def test_execution_ledger_uses_uuid_organization_id() -> None:
    column = ToolExecutionLedger.__table__.c.organization_id

    assert isinstance(column.type, Uuid)


def test_execution_ledger_has_required_columns() -> None:
    columns = ToolExecutionLedger.__table__.columns

    required = {
        "id",
        "organization_id",
        "idempotency_key",
        "tool_name",
        "state",
        "owner_token",
        "result_json",
        "claimed_at",
        "completed_at",
        "created_at",
        "updated_at",
    }

    assert required.issubset(set(columns.keys()))


def test_execution_ledger_has_unique_tenant_key() -> None:
    table = ToolExecutionLedger.__table__

    constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        {
            column.name
            for column in constraint.columns
        } == {"organization_id", "idempotency_key"}
        for constraint in constraints
    )


def test_execution_ledger_requires_owner_and_state() -> None:
    columns = ToolExecutionLedger.__table__.columns

    assert columns["owner_token"].nullable is False
    assert columns["state"].nullable is False
    assert columns["idempotency_key"].nullable is False
