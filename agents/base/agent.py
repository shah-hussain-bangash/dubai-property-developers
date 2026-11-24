"""BaseAgent: the single place where agent execution concerns live.

Subclasses implement only ``execute``. ``run`` adds input validation, timeouts,
tracing, structured logging, error mapping and execution records, so no agent
re-implements orchestration plumbing.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, Field, SerializeAsAny, ValidationError

from agents.base.context import AgentDependencies, ExecutionContext
from core.exceptions.errors import AuthorizationError, PlatformError
from core.memory.base import ConversationMemory, ScopedMemoryProvider
from core.observability.context import set_correlation_id
from core.observability.logging import get_logger
from schemas.agents.models import AgentDescriptor, AgentRunStatus, ImplementationStatus
from tools.base import ToolCallContext, ToolResult

InT = TypeVar("InT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)

logger = get_logger("agents")


class AgentSpec(BaseModel):
    agent_id: str
    name: str
    description: str
    responsibilities: list[str]
    implementation_status: ImplementationStatus
    allowed_tools: frozenset[str] = frozenset()
    version: str = "0.1.0"
    default_timeout_seconds: float = 20.0
    status_notes: str = ""

    def descriptor(self, timeout_seconds: float | None = None) -> AgentDescriptor:
        return AgentDescriptor(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            responsibilities=self.responsibilities,
            implementation_status=self.implementation_status,
            allowed_tools=sorted(self.allowed_tools),
            timeout_seconds=timeout_seconds or self.default_timeout_seconds,
            version=self.version,
        )


class AgentConfig(BaseModel):
    timeout_seconds: float | None = None
    enabled: bool = True


class AgentError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    agent_id: str
    status: AgentRunStatus
    correlation_id: str
    # SerializeAsAny: serialize the concrete output model, not just the BaseModel base.
    output: SerializeAsAny[BaseModel] | None = None
    error: AgentError | None = None
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status in {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.PENDING_APPROVAL,
            AgentRunStatus.ESCALATED,
        }


class BaseAgent(ABC, Generic[InT, OutT]):  # noqa: UP046 -- Retain the public Generic/TypeVar API and runtime introspection.
    spec: ClassVar[AgentSpec]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    def __init__(self, deps: AgentDependencies, config: AgentConfig | None = None) -> None:
        self.deps = deps
        self.config = config or AgentConfig()

    @property
    def timeout_seconds(self) -> float:
        return self.config.timeout_seconds or self.spec.default_timeout_seconds

    def conversation_memory(self, ctx: ExecutionContext) -> ConversationMemory:
        if ctx.principal.tenant_id != ctx.tenant_id:
            raise AuthorizationError("Principal belongs to a different organization")
        if not isinstance(self.deps.memory, ScopedMemoryProvider):
            raise AuthorizationError("Memory backend does not support organization/agent scopes")
        return self.deps.memory.scoped(ctx.tenant_id, self.spec.agent_id)

    @abstractmethod
    async def execute(self, data: InT, ctx: ExecutionContext) -> OutT: ...

    def outcome_status(self, output: OutT) -> AgentRunStatus:
        """Override to report PENDING_APPROVAL / ESCALATED based on the output."""
        return AgentRunStatus.SUCCEEDED

    async def use_tool(
        self, ctx: ExecutionContext, tool_name: str, payload: dict[str, Any], *, reason: str = ""
    ) -> ToolResult:
        call_ctx = ToolCallContext(
            principal=ctx.principal,
            tenant_id=ctx.tenant_id,
            correlation_id=ctx.correlation_id,
            agent_id=self.spec.agent_id,
            allowed_tools=self.spec.allowed_tools,
        )
        return await self.deps.gateway.invoke(call_ctx, tool_name, payload, reason=reason)

    async def run(self, payload: InT | dict[str, Any], ctx: ExecutionContext) -> AgentResult:
        agent_id = self.spec.agent_id
        set_correlation_id(ctx.correlation_id)
        started = time.perf_counter()
        started_at = datetime.now(UTC)
        log_extra = {"agent_id": agent_id, "workflow_execution_id": ctx.workflow_execution_id}

        def _result(status: AgentRunStatus, **kwargs: Any) -> AgentResult:
            return AgentResult(
                agent_id=agent_id,
                status=status,
                correlation_id=ctx.correlation_id,
                duration_ms=int((time.perf_counter() - started) * 1000),
                **kwargs,
            )

        if not self.config.enabled:
            result = _result(
                AgentRunStatus.FAILED,
                error=AgentError(code="agent_disabled", message="agent is disabled"),
            )
            await self._record(result, started_at)
            return result

        try:
            data = (
                payload
                if isinstance(payload, self.input_model)
                else self.input_model.model_validate(payload)
            )
        except ValidationError as exc:
            result = _result(
                AgentRunStatus.FAILED,
                error=AgentError(
                    code="invalid_input",
                    message="input failed validation",
                    details={
                        "errors": exc.errors(
                            include_input=False, include_url=False, include_context=False
                        )
                    },
                ),
            )
            await self._record(result, started_at)
            return result

        logger.info("agent started", extra=log_extra)
        try:
            with self.deps.tracer.span(
                f"agent.{agent_id}", agent=agent_id, correlation_id=ctx.correlation_id
            ):
                output = await asyncio.wait_for(
                    self.execute(data, ctx),  # type: ignore[arg-type]
                    timeout=self.timeout_seconds,
                )
            result = _result(self.outcome_status(output), output=output)
        except TimeoutError:
            logger.warning("agent timed out", extra=log_extra)
            result = _result(
                AgentRunStatus.TIMED_OUT,
                error=AgentError(code="agent_timeout", message=f"exceeded {self.timeout_seconds}s"),
            )
        except PlatformError as exc:
            logger.warning("agent failed", extra={**log_extra, "error_code": exc.code})
            result = _result(
                AgentRunStatus.FAILED,
                error=AgentError(code=exc.code, message=exc.message, details=exc.details),
            )
        except Exception:
            logger.exception("agent crashed", extra=log_extra)
            result = _result(
                AgentRunStatus.FAILED,
                error=AgentError(code="internal_error", message="unexpected agent error"),
            )
        logger.info(
            "agent finished",
            extra={**log_extra, "status": result.status.value, "duration_ms": result.duration_ms},
        )
        await self._record(result, started_at)
        return result

    async def _record(self, result: AgentResult, started_at: datetime) -> None:
        await self.deps.executions.record(
            {
                "agent_id": result.agent_id,
                "status": result.status.value,
                "correlation_id": result.correlation_id,
                "error_code": result.error.code if result.error else None,
                "duration_ms": result.duration_ms,
                "started_at": started_at.isoformat(),
            }
        )
