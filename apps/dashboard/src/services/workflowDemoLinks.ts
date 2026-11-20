import type { WorkflowDescriptor } from '@/types/api';

export interface WorkflowDemoLink { href: string; label: string; description: string }

export function workflowDemoLink(workflow: WorkflowDescriptor): WorkflowDemoLink | null {
  if (workflow.implementation_status === 'interface_only') return null;
  switch (workflow.workflow_id) {
    case 'lead_processing': return { href:'/leads', label:'Open fictional lead workflow demo', description:'Process a fictional lead with mock CRM storage.' };
    case 'property_recommendation': return { href:'/properties', label:'Open fictional property workflow demo', description:'Match fictional properties, inspect caveats and compare a shortlist.' };
    case 'sales_conversation': return { href:'/conversations', label:'Open fictional reply workflow demo', description:'Prepare an unsent web-chat draft or see a request for staff review.' };
    case 'knowledge_support': return { href:'/knowledge', label:'Open fictional knowledge workflow demo', description:'Prepare a cited answer from public fictional documents.' };
    default: return null;
  }
}
