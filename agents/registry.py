"""Agent registry: the single list of the platform's 13 agents."""

from __future__ import annotations

from typing import Any

from agents.analytics.agent import AnalyticsAgent
from agents.base.agent import AgentConfig, BaseAgent
from agents.base.context import AgentDependencies
from agents.crm.agent import CRMAgent
from agents.documents.agent import DocumentAgent
from agents.email.agent import EmailAgent
from agents.followup.agent import FollowUpAgent
from agents.lead_intake.agent import LeadIntakeAgent
from agents.marketing.agent import MarketingAgent
from agents.property_recommendation.agent import PropertyRecommendationAgent
from agents.qualification.agent import QualificationAgent
from agents.sales_conversation.agent import SalesConversationAgent
from agents.supervisor.agent import SupervisorAgent
from agents.voice.agent import VoiceAgent
from agents.whatsapp.agent import WhatsAppAgent
from core.exceptions.errors import AgentNotFoundError
from schemas.agents.models import AgentDescriptor

AGENT_CLASSES: tuple[type[BaseAgent[Any, Any]], ...] = (
    SupervisorAgent,
    LeadIntakeAgent,
    QualificationAgent,
    PropertyRecommendationAgent,
    SalesConversationAgent,
    FollowUpAgent,
    CRMAgent,
    EmailAgent,
    WhatsAppAgent,
    VoiceAgent,
    MarketingAgent,
    DocumentAgent,
    AnalyticsAgent,
)


def agent_descriptors(default_timeout: float | None = None) -> list[AgentDescriptor]:
    return [cls.spec.descriptor(default_timeout) for cls in AGENT_CLASSES]


class AgentRegistry:
    def __init__(
        self,
        deps: AgentDependencies,
        configs: dict[str, AgentConfig] | None = None,
        default_timeout: float | None = None,
    ) -> None:
        configs = configs or {}
        self._agents: dict[str, BaseAgent[Any, Any]] = {}
        for cls in AGENT_CLASSES:
            agent_id = cls.spec.agent_id
            if agent_id in self._agents:
                raise ValueError(f"duplicate agent id {agent_id}")
            config = configs.get(agent_id) or AgentConfig(timeout_seconds=default_timeout)
            self._agents[agent_id] = cls(deps, config)

    def get(self, agent_id: str) -> BaseAgent[Any, Any]:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise AgentNotFoundError(f"agent '{agent_id}' is not registered") from exc

    def ids(self) -> list[str]:
        return list(self._agents)

    def descriptors(self) -> list[AgentDescriptor]:
        return [a.spec.descriptor(a.timeout_seconds) for a in self._agents.values()]

    def __len__(self) -> int:
        return len(self._agents)
