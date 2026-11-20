/**
 * Dashboard-side domain types used by demo data and UI views.
 * These are NOT backend contracts (see ./api.ts for those).
 */

export type LeadCategory = 'hot' | 'warm' | 'cold';

export type LeadStatus =
  | 'new'
  | 'qualifying'
  | 'qualified'
  | 'nurturing'
  | 'handed_off'
  | 'closed_lost';

export type LeadSource =
  | 'website'
  | 'whatsapp'
  | 'portal_listing'
  | 'referral'
  | 'social_ads'
  | 'walk_in';

export interface Lead {
  id: string;
  name: string;
  phone: string;
  email: string;
  source: LeadSource;
  score: number;
  category: LeadCategory;
  status: LeadStatus;
  assignedAgent: string;
  interest: string;
  createdAt: string;
}

export type ConversationChannel = 'whatsapp' | 'email' | 'web';

export type MessageSender = 'lead' | 'agent' | 'human';

export interface ConversationMessage {
  id: string;
  sender: MessageSender;
  author: string;
  text: string;
  sentAt: string;
}

export interface Conversation {
  id: string;
  leadName: string;
  channel: ConversationChannel;
  subject: string;
  handledBy: string;
  lastMessageAt: string;
  escalated: boolean;
  escalationReason?: string;
  messages: ConversationMessage[];
}

export type PropertyStatus = 'available' | 'reserved' | 'off_plan';

export interface PropertyUnit {
  id: string;
  project: string;
  community: string;
  developer: string;
  unitType: 'Apartment' | 'Villa' | 'Townhouse' | 'Penthouse';
  bedrooms: number;
  sizeSqft: number;
  /** Illustrative only — NOT a market price. */
  illustrativePriceAed: number;
  status: PropertyStatus;
  handover: string;
}

export type AccessLevel = 'public' | 'internal' | 'restricted';

export interface KnowledgeDocument {
  id: string;
  title: string;
  category: string;
  version: string;
  owner: string;
  updatedAt: string;
  reviewIntervalDays: number;
  access: AccessLevel;
}

export type IntegrationMode = 'mock' | 'not_configured' | 'pending_access';

export interface Integration {
  id: string;
  name: string;
  category: string;
  mode: IntegrationMode;
  description: string;
  note: string;
}

export type ActivityOutcome = 'success' | 'pending_approval' | 'failed' | 'skipped';

export interface AgentActivity {
  id: string;
  agentId: string;
  agentName: string;
  action: string;
  subject: string;
  at: string;
  outcome: ActivityOutcome;
}

export interface ChartDatum {
  label: string;
  value: number;
}

export interface Kpi {
  id: string;
  label: string;
  value: string;
  delta?: string;
  deltaTone?: 'positive' | 'negative' | 'neutral';
  hint?: string;
  trend?: number[];
}
