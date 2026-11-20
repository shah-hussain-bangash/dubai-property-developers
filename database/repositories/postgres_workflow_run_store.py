"""PostgreSQL persistence for workflow execution history.

Uses the existing workflow_executions table.

Stores execution metadata and step summaries only.
Raw workflow state, customer information, and error details
are deliberately excluded from this history store.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models.agent import WorkflowExecution
from database.models.identity import Organization
from workflows.engine.core import WorkflowRun


class PostgresWorkflowRunStore:
    """Tenant-scoped PostgreSQL workflow execution store."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def _organization_id(
        self,
        session: AsyncSession,
        tenant_id: str,
    ) -> uuid.UUID:
        if not tenant_id:
            raise ValueError("tenant_id is required")

        organization_id = await session.scalar(
            select(Organization.id).where(
                Organization.slug == tenant_id,
                Organization.is_active.is_(True),
            )
        )

        if organization_id is None:
            raise ValueError(f"Unknown or inactive organization: {tenant_id}")

        return organization_id

    @staticmethod
    def _safe_step_history(run: WorkflowRun) -> dict:
        """Persist only non-sensitive execution metadata."""

        return {
            "schema_version": 1,
            "step_count": len(run.steps),
            "steps": [
                {
                    "name": step.name,
                    "outcome": step.outcome,
                    "duration_ms": step.duration_ms,
                    "error_code": step.error_code,
                }
                for step in run.steps
            ],
        }

    async def save(self, run: WorkflowRun) -> None:
        """Insert or update a workflow execution atomically."""

        execution_id = uuid.UUID(run.execution_id)

        if not run.workflow_id:
            raise ValueError("workflow_id is required")

        safe_history = self._safe_step_history(run)

        async with self.session_factory() as session, session.begin():
            organization_id = await self._organization_id(
                session,
                run.tenant_id,
            )

            existing = await session.scalar(
                select(WorkflowExecution)
                .where(WorkflowExecution.id == execution_id)
                .with_for_update()
            )

            if existing is not None:
                if existing.organization_id != organization_id:
                    raise ValueError("Workflow execution belongs to another organization")

                if existing.workflow_key != run.workflow_id:
                    raise ValueError("Workflow identity cannot be changed")

                record = existing

            else:
                record = WorkflowExecution(
                    id=execution_id,
                    organization_id=organization_id,
                    workflow_key=run.workflow_id,
                )
                session.add(record)

            record.status = run.status.value
            record.correlation_id = run.correlation_id
            record.current_step = run.current_step
            record.state = safe_history

            record.error_code = (
                str(run.error.get("code", "workflow_error"))[:64] if run.error else None
            )

            # Never persist raw exception text or customer details.
            record.error_message = "Workflow execution failed" if run.error else None

            record.started_at = run.started_at
            record.finished_at = run.finished_at

    async def get(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> WorkflowExecution | None:
        """Retrieve execution metadata within one organization."""

        parsed_id = uuid.UUID(execution_id)

        async with self.session_factory() as session:
            organization_id = await self._organization_id(
                session,
                tenant_id,
            )

            return await session.scalar(
                select(WorkflowExecution).where(
                    WorkflowExecution.id == parsed_id,
                    WorkflowExecution.organization_id == organization_id,
                )
            )
