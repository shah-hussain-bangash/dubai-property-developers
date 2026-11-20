"""Tool contracts and the ToolGateway.

Agents never call integrations directly. Every tool call goes through
ToolGateway, which:

1. Checks the calling agent's tool allowlist.
2. Validates the payload.
3. Generates a tenant-scoped idempotency key.
4. Checks RBAC before returning a cached execution result.
5. Creates a human approval request when required.
6. Checks RBAC before executing an action.
7. Audits execution and caches successful results.

Agents may request human approval without having permission to
execute the action themselves.

Side effects sharing an idempotency store are serialized within one event loop.
Successful actions return cached results on subsequent replays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, Field

from core.events.audit import AuditEvent, AuditSink, InMemoryAuditSink
from core.exceptions.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ToolPermissionError,
)
from core.observability.logging import get_logger
from core.observability.tracing import NoopTracer, Tracer
from core.policies.actions import (
    SIDE_EFFECT_CATEGORIES,
    ActionCategory,
    ApprovalPolicy,
)
from core.policies.approvals import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStore,
    InMemoryApprovalStore,
)
from core.resilience.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    make_idempotency_key,
)
from core.security.rbac import Permission, Principal

logger = get_logger(__name__)

IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600


class ToolSpec(BaseModel):
    name: str
    description: str
    category: ActionCategory
    permission: Permission | None = None


class ToolResultStatus(StrEnum):
    EXECUTED = "executed"
    PENDING_APPROVAL = "pending_approval"
    REPLAYED = "replayed"


class ToolResult(BaseModel):
    tool: str
    status: ToolResultStatus
    data: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = None
    idempotency_key: str | None = None


class Tool(Protocol):
    spec: ClassVar[ToolSpec]

    def validate(self, payload: dict[str, Any]) -> None:
        """Validate the payload before execution."""
        ...

    async def execute(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class BaseTool:
    """Convenience base with no additional validation by default."""

    spec: ClassVar[ToolSpec]

    def validate(self, payload: dict[str, Any]) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    principal: Principal
    tenant_id: str
    correlation_id: str
    agent_id: str | None = None
    allowed_tools: frozenset[str] = field(default_factory=frozenset)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.spec.name

        if name in self._tools:
            raise ValueError(f"tool {name} already registered")

        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise NotFoundError(f"tool {name} not registered") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in self.names()]


class ToolGateway:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        approval_policy: ApprovalPolicy | None = None,
        approvals: ApprovalStore | None = None,
        idempotency: IdempotencyStore | None = None,
        audit: AuditSink | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.registry = registry
        self.approval_policy = approval_policy or ApprovalPolicy()

        self.approvals: ApprovalStore = approvals or InMemoryApprovalStore()

        self.idempotency: IdempotencyStore = idempotency or InMemoryIdempotencyStore()

        self.audit: AuditSink = audit or InMemoryAuditSink()
        self.tracer: Tracer = tracer or NoopTracer()

    async def _audit(
        self,
        ctx: ToolCallContext,
        tool: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self.audit.record(
            AuditEvent(
                tenant_id=ctx.tenant_id,
                actor=(
                    f"{ctx.principal.subject}" + (f"/agent:{ctx.agent_id}" if ctx.agent_id else "")
                ),
                action=f"tool:{tool}",
                resource_type="tool",
                resource_id=tool,
                outcome=outcome,
                correlation_id=ctx.correlation_id,
                details=details or {},
            )
        )

    async def _authorize(
        self,
        ctx: ToolCallContext,
        spec: ToolSpec,
    ) -> None:
        """Check RBAC permissions and audit denials.

        Authorization is required before executing an action
        or returning a cached execution result.
        """

        if spec.permission is not None and not ctx.principal.has(spec.permission):
            await self._audit(
                ctx,
                spec.name,
                "denied",
                {
                    "missing_permission": spec.permission.value,
                },
            )

            raise AuthorizationError(f"principal lacks permission {spec.permission.value}")

    async def invoke(
        self,
        ctx: ToolCallContext,
        tool_name: str,
        payload: dict[str, Any],
        *,
        reason: str = "",
    ) -> ToolResult:
        tool = self.registry.get(tool_name)
        spec = tool.spec

        # 1. Enforce the agent tool allowlist.
        if ctx.agent_id is not None and tool_name not in ctx.allowed_tools:
            await self._audit(
                ctx,
                tool_name,
                "denied",
                {"why": "not in agent allowlist"},
            )

            raise ToolPermissionError(f"agent '{ctx.agent_id}' may not use tool '{tool_name}'")

        # 2. Validate tool-specific business rules.
        tool.validate(payload)

        # 3. Generate a tenant-scoped idempotency key.
        side_effect = spec.category in SIDE_EFFECT_CATEGORIES

        key = make_idempotency_key(
            tool_name,
            payload,
            scope=ctx.tenant_id,
        )

        # 4. Check cached results.
        #
        # Do not require execution permission on a cache miss:
        # agents may still need to request human approval.
        #
        # On a cache hit, check RBAC before returning the result.
        if side_effect:
            cached = await self.idempotency.get(key)

            if cached is not None:
                await self._authorize(ctx, spec)

                return ToolResult(
                    tool=tool_name,
                    status=ToolResultStatus.REPLAYED,
                    data=cached,
                    idempotency_key=key,
                )

        # 5. Handle human approval requirements.
        if self.approval_policy.requires_approval(spec.category):
            existing = await self.approvals.find_by_idempotency_key(key)

            if existing is None or existing.status in {
                ApprovalStatus.REJECTED,
                ApprovalStatus.EXPIRED,
            }:
                existing = await self.approvals.create(
                    ApprovalRequest(
                        tenant_id=ctx.tenant_id,
                        tool_name=tool_name,
                        action_category=spec.category.value,
                        requested_by=ctx.principal.subject,
                        requested_by_agent=ctx.agent_id,
                        reason=reason or spec.description,
                        payload=payload,
                        idempotency_key=key,
                        correlation_id=ctx.correlation_id,
                    )
                )

                await self._audit(
                    ctx,
                    tool_name,
                    "pending_approval",
                    {
                        "approval_id": existing.approval_id,
                    },
                )

            if existing.status != ApprovalStatus.APPROVED:
                return ToolResult(
                    tool=tool_name,
                    status=ToolResultStatus.PENDING_APPROVAL,
                    approval_id=existing.approval_id,
                    idempotency_key=key,
                )

            # Approval exists for this exact payload.
            # RBAC is checked again before execution.

        return await self._execute(
            ctx,
            tool,
            payload,
            key if side_effect else None,
        )

    async def execute_approved(
        self,
        approval_id: str,
        approver: Principal,
    ) -> ToolResult:
        """Execute or replay an approved action.

        Store-scoped locking protects gateways sharing one store instance.
        It does not provide distributed exactly-once guarantees.
        """

        request = await self.approvals.get(approval_id)

        if request.status != ApprovalStatus.APPROVED:
            raise ConflictError(f"approval {approval_id} is {request.status}, not approved")

        if request.tenant_id != approver.tenant_id:
            raise AuthorizationError("approver belongs to a different organization")

        tool = self.registry.get(request.tool_name)
        spec = tool.spec

        ctx = ToolCallContext(
            principal=approver,
            tenant_id=request.tenant_id,
            correlation_id=request.correlation_id or "",
        )

        tool.validate(request.payload)

        # RBAC must pass before cached results are returned.
        await self._authorize(ctx, spec)

        side_effect = spec.category in SIDE_EFFECT_CATEGORIES

        if not side_effect:
            return await self._execute(
                ctx,
                tool,
                request.payload,
                None,
            )

        key = request.idempotency_key

        return await self._execute(
            ctx,
            tool,
            request.payload,
            key,
        )

    async def _execute(
        self,
        ctx: ToolCallContext,
        tool: Tool,
        payload: dict[str, Any],
        key: str | None,
    ) -> ToolResult:
        # Every entry point checks authorization before waiting or replaying.
        await self._authorize(ctx, tool.spec)
        if key is None:
            return await self._execute_once(ctx, tool, payload, None)

        async with self.idempotency.execution_lock(key):
            # Another gateway may have completed this action while we waited.
            cached = await self.idempotency.get(key)

            if cached is not None:
                return ToolResult(
                    tool=tool.spec.name,
                    status=ToolResultStatus.REPLAYED,
                    data=cached,
                    idempotency_key=key,
                )

            # Keep the shared lock until execution and cache storage finish.
            return await self._execute_once(ctx, tool, payload, key)

    async def _execute_once(
        self,
        ctx: ToolCallContext,
        tool: Tool,
        payload: dict[str, Any],
        key: str | None,
    ) -> ToolResult:
        spec = tool.spec

        # Defense in depth: check RBAC before actual execution.
        await self._authorize(ctx, spec)

        with self.tracer.span(
            f"tool.{spec.name}",
            tool=spec.name,
            agent=ctx.agent_id,
        ):
            try:
                data = await tool.execute(payload)

            except Exception as exc:
                await self._audit(
                    ctx,
                    spec.name,
                    "failed",
                    {
                        "error": type(exc).__name__,
                    },
                )
                raise

        # Cache successful results for subsequent sequential replays.
        if key is not None:
            await self.idempotency.put(
                key,
                data,
                IDEMPOTENCY_TTL_SECONDS,
            )

        if spec.category != ActionCategory.READ:
            await self._audit(
                ctx,
                spec.name,
                "executed",
                {
                    "result_keys": sorted(data),
                },
            )

        return ToolResult(
            tool=spec.name,
            status=ToolResultStatus.EXECUTED,
            data=data,
            idempotency_key=key,
        )
