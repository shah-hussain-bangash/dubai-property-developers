import type { ImplementationStatus, WorkflowDescriptor } from '@/types/api';

export type WorkflowStatusFilter = 'all' | ImplementationStatus;

export function filterWorkflows(items: WorkflowDescriptor[], query: string, status: WorkflowStatusFilter): WorkflowDescriptor[] {
  const term = query.trim().toLocaleLowerCase();
  return items.filter(item => (status === 'all' || item.implementation_status === status)
    && (!term || [item.workflow_id, item.name, item.description, ...item.steps.flatMap(step => [step, step.replaceAll('_', ' ')])]
      .some(text => text.toLocaleLowerCase().includes(term))));
}
