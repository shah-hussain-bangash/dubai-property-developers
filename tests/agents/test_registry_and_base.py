from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from pydantic import BaseModel

from agents.base.agent import AgentConfig, AgentSpec, BaseAgent
from agents.base.context import AgentDependencies, ExecutionContext
from agents.registry import AGENT_CLASSES, agent_descriptors
from core.exceptions.errors import DomainValidationError, ToolPermissionError
from schemas.agents.models import AgentRunStatus, ImplementationStatus
from tools.base import ToolGateway, ToolRegistry
from workflows.runtime import PlatformRuntime

EXPECTED_AGENTS = {
    "supervisor", "lead_intake", "qualification", "property_recommendation", "sales_conversation",
    "followup", "crm", "email", "whatsapp", "voice", "marketing", "documents", "analytics",
}


def test_registry_contains_exactly_13_unique_agents(runtime: PlatformRuntime) -> None:
    assert len(AGENT_CLASSES) == 13
    assert set(runtime.agents.ids()) == EXPECTED_AGENTS
    assert len(runtime.agents) == 13


def test_every_agent_contract_is_complete(runtime: PlatformRuntime) -> None:
    registered_tools = set(runtime.tools.names())
    for descriptor in agent_descriptors():
        assert descriptor.responsibilities, descriptor.agent_id
        assert descriptor.timeout_seconds > 0
        assert set(descriptor.allowed_tools) <= registered_tools, descriptor.agent_id
    for cls in AGENT_CLASSES:
        assert issubclass(cls.input_model, BaseModel) and issubclass(cls.output_model, BaseModel)
    statuses = {d.agent_id: d.implementation_status for d in agent_descriptors()}
    assert statuses["voice"] == ImplementationStatus.INTERFACE_ONLY


class _In(BaseModel):
    delay: float = 0.0
    fail: bool = False


class _Out(BaseModel):
    ok: bool = True


class _ProbeAgent(BaseAgent[_In, _Out]):
    spec: ClassVar[AgentSpec] = AgentSpec(
        agent_id="probe",
        name="Probe",
        description="test agent",
        responsibilities=["test"],
        implementation_status=ImplementationStatus.FUNCTIONAL,
    )
    input_model = _In
    output_model = _Out

    async def execute(self, data: _In, ctx: ExecutionContext) -> _Out:
        await asyncio.sleep(data.delay)
        if data.fail:
            raise DomainValidationError("bad request")
        return _Out()


def _probe(timeout: float = 1.0) -> _ProbeAgent:
    return _ProbeAgent(AgentDependencies(gateway=ToolGateway(ToolRegistry())), AgentConfig(timeout_seconds=timeout))


async def test_base_agent_success_timeout_error_and_validation(system_ctx: ExecutionContext) -> None:
    ok = await _probe().run({}, system_ctx)
    assert ok.status == AgentRunStatus.SUCCEEDED and ok.output is not None

    slow = await _probe(timeout=0.05).run({"delay": 1}, system_ctx)
    assert slow.status == AgentRunStatus.TIMED_OUT and slow.error and slow.error.code == "agent_timeout"

    failed = await _probe().run({"fail": True}, system_ctx)
    assert failed.status == AgentRunStatus.FAILED and failed.error and failed.error.code == "validation_error"

    invalid = await _probe().run({"delay": "not-a-number"}, system_ctx)
    assert invalid.error and invalid.error.code == "invalid_input"


async def test_disabled_agent_does_not_run(system_ctx: ExecutionContext) -> None:
    agent = _ProbeAgent(AgentDependencies(gateway=ToolGateway(ToolRegistry())), AgentConfig(enabled=False))
    result = await agent.run({}, system_ctx)
    assert result.error and result.error.code == "agent_disabled"


async def test_agent_cannot_use_tools_outside_allowlist(
    runtime: PlatformRuntime, ctx: ExecutionContext
) -> None:
    agent = runtime.agents.get("marketing")  # allowlist is empty
    with pytest.raises(ToolPermissionError):
        await agent.use_tool(ctx, "property.search", {})
