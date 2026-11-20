"""Per-call execution context and long-lived agent dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from core.events.bus import EventBus, InMemoryEventBus
from core.llm.router import ModelRouter
from core.memory.base import ConversationMemory, InMemoryConversationMemory
from core.observability.context import new_correlation_id
from core.observability.tracing import NoopTracer, Tracer
from core.security.rbac import SYSTEM_PRINCIPAL, Principal
from tools.base import ToolGateway


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    principal: Principal
    tenant_id: str
    correlation_id: str = field(default_factory=new_correlation_id)
    workflow_execution_id: str | None = None

    @classmethod
    def system(cls, tenant_id: str | None = None, correlation_id: str | None = None) -> ExecutionContext:
        return cls(
            principal=SYSTEM_PRINCIPAL,
            tenant_id=tenant_id or SYSTEM_PRINCIPAL.tenant_id,
            correlation_id=correlation_id or new_correlation_id(),
        )


class ExecutionRecorder(Protocol):
    async def record(self, record: dict[str, Any]) -> None: ...


class InMemoryExecutionRecorder:
    def __init__(self, max_records: int = 1000) -> None:
        self.records: list[dict[str, Any]] = []
        self._max = max_records

    async def record(self, record: dict[str, Any]) -> None:
        self.records.append(record)
        del self.records[: -self._max]


@dataclass
class AgentDependencies:
    gateway: ToolGateway
    llm: ModelRouter | None = None
    memory: ConversationMemory = field(default_factory=InMemoryConversationMemory)
    events: EventBus = field(default_factory=InMemoryEventBus)
    tracer: Tracer = field(default_factory=NoopTracer)
    executions: ExecutionRecorder = field(default_factory=InMemoryExecutionRecorder)
