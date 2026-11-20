import type { AgentDescriptor } from '@/types/api';

export interface AgentDemoLink { href: string; label: string; description: string }

export function agentDemoLink(agent: AgentDescriptor): AgentDemoLink | null {
  if (agent.implementation_status === 'interface_only') return null;
  switch (agent.agent_id) {
    case 'lead_intake': return { href:'/leads', label:'Open fictional lead demo', description:'Enter fictional requirements to see lead intake and qualification.' };
    case 'qualification': return { href:'/workflows', label:'Open fictional qualification demo', description:'Run a guided scenario and inspect its score rules and reasons.' };
    case 'property_recommendation': return { href:'/properties', label:'Open fictional property demo', description:'Match fictional listings and compare a shortlist with source dates and caveats.' };
    case 'sales_conversation': return { href:'/conversations', label:'Open fictional reply demo', description:'Prepare an unsent reply draft or see a request for staff review.' };
    case 'documents': return { href:'/knowledge', label:'Open fictional knowledge demo', description:'Ask about public fictional documents and inspect the cited passages.' };
    default: return null;
  }
}
