import type { AgentDescriptor, ImplementationStatus } from '@/types/api';

export type AgentStatusFilter = 'all' | ImplementationStatus;

export function filterAgents(items: AgentDescriptor[], query: string, status: AgentStatusFilter): AgentDescriptor[] {
  const term = query.trim().toLocaleLowerCase();
  return items.filter(agent => (status === 'all' || agent.implementation_status === status)
    && (!term || [agent.agent_id, agent.name, agent.description, ...agent.responsibilities, ...agent.allowed_tools]
      .some(text => text.toLocaleLowerCase().includes(term))));
}
