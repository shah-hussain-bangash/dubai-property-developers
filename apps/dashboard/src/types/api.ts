/**
 * Backend API contract types. These mirror the FastAPI response models
 * exactly — keep field names in snake_case to match the wire format.
 */

export type ImplementationStatus = 'functional' | 'partial' | 'interface_only';

export const IMPLEMENTATION_STATUSES: readonly ImplementationStatus[] = [
  'functional',
  'partial',
  'interface_only',
];

export type AgentId =
  | 'supervisor'
  | 'lead_intake'
  | 'qualification'
  | 'property_recommendation'
  | 'sales_conversation'
  | 'followup'
  | 'crm'
  | 'email'
  | 'whatsapp'
  | 'voice'
  | 'marketing'
  | 'documents'
  | 'analytics';

export type WorkflowId =
  | 'lead_processing'
  | 'property_recommendation'
  | 'sales_conversation'
  | 'followup_automation'
  | 'crm_sync'
  | 'knowledge_support';

export interface AgentDescriptor {
  /** Backend may add agents later, so this stays a plain string on the wire. */
  agent_id: string;
  name: string;
  description: string;
  responsibilities: string[];
  implementation_status: ImplementationStatus;
  allowed_tools: string[];
  timeout_seconds: number;
  version: string;
}

export interface WorkflowDescriptor {
  workflow_id: string;
  name: string;
  description: string;
  steps: string[];
  implementation_status: ImplementationStatus;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

export type AgentListResponse = ListResponse<AgentDescriptor>;
export type WorkflowListResponse = ListResponse<WorkflowDescriptor>;

export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
  environment: string;
}
