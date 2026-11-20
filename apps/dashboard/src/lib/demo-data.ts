/**
 * DEMO DATA — every record in this file is fictional.
 *
 * - Names follow the "Demo Lead NN" pattern, phones use +971 50 000 00xx,
 *   emails use @example.com, projects/developers are suffixed "(Fictional)".
 * - Prices are illustrative placeholders, NOT market data or valuations.
 * - Any page rendering this data must also render <DemoDataBanner />.
 */

import type {
  AgentDescriptor,
  AgentListResponse,
  WorkflowDescriptor,
  WorkflowListResponse,
} from '@/types/api';
import type {
  AgentActivity,
  ChartDatum,
  Conversation,
  Integration,
  KnowledgeDocument,
  Kpi,
  Lead,
  PropertyUnit,
} from '@/types/domain';

/** Fixed "now" for demo calculations so renders are deterministic. */
export const DEMO_REFERENCE_DATE = '2026-10-08T08:00:00Z';

// ---------------------------------------------------------------------------
// Agents (fallback for GET /api/v1/agents)
// ---------------------------------------------------------------------------

export const DEMO_AGENTS: AgentDescriptor[] = [
  {
    agent_id: 'supervisor',
    name: 'Supervisor Agent',
    description: 'Routes tasks between specialist agents and enforces approval policies.',
    responsibilities: ['Route incoming tasks', 'Enforce human-approval gates', 'Track task outcomes'],
    implementation_status: 'functional',
    allowed_tools: ['route_task', 'request_human_approval', 'read_agent_registry'],
    timeout_seconds: 30,
    version: '0.1.0',
  },
  {
    agent_id: 'lead_intake',
    name: 'Lead Intake Agent',
    description: 'Captures leads from inbound channels, normalises contact details and deduplicates.',
    responsibilities: ['Normalise contact data', 'Deduplicate leads', 'Create CRM lead records'],
    implementation_status: 'functional',
    allowed_tools: ['normalize_contact', 'deduplicate_lead', 'crm.create_lead'],
    timeout_seconds: 20,
    version: '0.1.0',
  },
  {
    agent_id: 'qualification',
    name: 'Qualification Agent',
    description: 'Scores leads on budget, timeline, intent and financing readiness.',
    responsibilities: ['Score leads', 'Categorise hot / warm / cold', 'Flag missing information'],
    implementation_status: 'functional',
    allowed_tools: ['score_lead', 'crm.update_lead', 'knowledge.search'],
    timeout_seconds: 30,
    version: '0.1.0',
  },
  {
    agent_id: 'property_recommendation',
    name: 'Property Recommendation Agent',
    description: 'Matches qualified leads to inventory based on stated preferences.',
    responsibilities: ['Search inventory', 'Rank matching units', 'Explain recommendations'],
    implementation_status: 'functional',
    allowed_tools: ['inventory.search', 'knowledge.search'],
    timeout_seconds: 45,
    version: '0.1.0',
  },
  {
    agent_id: 'sales_conversation',
    name: 'Sales Conversation Agent',
    description: 'Drafts replies to lead questions using approved knowledge sources.',
    responsibilities: ['Draft replies', 'Answer FAQs from knowledge base', 'Escalate sensitive topics'],
    implementation_status: 'partial',
    allowed_tools: ['knowledge.search', 'draft_reply', 'request_human_approval'],
    timeout_seconds: 60,
    version: '0.1.0',
  },
  {
    agent_id: 'followup',
    name: 'Follow-up Agent',
    description: 'Schedules and drafts follow-ups for leads that have gone quiet.',
    responsibilities: ['Schedule follow-ups', 'Draft reminder messages'],
    implementation_status: 'partial',
    allowed_tools: ['schedule_task', 'draft_reply'],
    timeout_seconds: 30,
    version: '0.1.0',
  },
  {
    agent_id: 'crm',
    name: 'CRM Agent',
    description: 'Reads and updates CRM records and tasks.',
    responsibilities: ['Sync lead status', 'Create CRM tasks', 'Log activities'],
    implementation_status: 'functional',
    allowed_tools: ['crm.read_lead', 'crm.update_lead', 'crm.create_task'],
    timeout_seconds: 30,
    version: '0.1.0',
  },
  {
    agent_id: 'email',
    name: 'Email Agent',
    description: 'Drafts outbound emails; sending is mocked until a provider is configured.',
    responsibilities: ['Draft emails', 'Apply templates'],
    implementation_status: 'partial',
    allowed_tools: ['email.draft', 'email.send_mock'],
    timeout_seconds: 30,
    version: '0.1.0',
  },
  {
    agent_id: 'whatsapp',
    name: 'WhatsApp Agent',
    description: 'Handles WhatsApp template messages through a mock connector.',
    responsibilities: ['Send template messages (mock)', 'Read inbound messages (mock)'],
    implementation_status: 'partial',
    allowed_tools: ['whatsapp.send_template_mock', 'whatsapp.read_inbox_mock'],
    timeout_seconds: 30,
    version: '0.1.0',
  },
  {
    agent_id: 'voice',
    name: 'Voice Agent',
    description: 'Interface for future telephony call handling. Not implemented.',
    responsibilities: ['Place and summarise calls (planned)'],
    implementation_status: 'interface_only',
    allowed_tools: ['telephony.call_mock'],
    timeout_seconds: 120,
    version: '0.0.1',
  },
  {
    agent_id: 'marketing',
    name: 'Marketing Agent',
    description: 'Drafts campaign copy and audience segments for review.',
    responsibilities: ['Draft campaign copy', 'Suggest audience segments'],
    implementation_status: 'partial',
    allowed_tools: ['campaign.draft', 'audience.segment'],
    timeout_seconds: 60,
    version: '0.1.0',
  },
  {
    agent_id: 'documents',
    name: 'Documents Agent',
    description: 'Extracts and classifies information from uploaded documents.',
    responsibilities: ['Extract document fields', 'Classify document types'],
    implementation_status: 'partial',
    allowed_tools: ['documents.extract', 'documents.classify'],
    timeout_seconds: 90,
    version: '0.1.0',
  },
  {
    agent_id: 'analytics',
    name: 'Analytics Agent',
    description: 'Aggregates pipeline metrics and generates summary reports.',
    responsibilities: ['Query metrics', 'Generate summary reports'],
    implementation_status: 'partial',
    allowed_tools: ['metrics.query', 'report.generate'],
    timeout_seconds: 60,
    version: '0.1.0',
  },
];

export const DEMO_AGENTS_RESPONSE: AgentListResponse = {
  items: DEMO_AGENTS,
  total: DEMO_AGENTS.length,
};

// ---------------------------------------------------------------------------
// Workflows (fallback for GET /api/v1/workflows)
// ---------------------------------------------------------------------------

export const DEMO_WORKFLOWS: WorkflowDescriptor[] = [
  {
    workflow_id: 'lead_processing',
    name: 'Lead Processing',
    description: 'Takes a new inbound lead from capture through qualification and CRM creation.',
    steps: ['lead_intake', 'qualification', 'crm', 'supervisor'],
    implementation_status: 'functional',
  },
  {
    workflow_id: 'property_recommendation',
    name: 'Property Recommendation',
    description: 'Matches a qualified lead with inventory and prepares a shortlist for review.',
    steps: ['qualification', 'property_recommendation', 'supervisor'],
    implementation_status: 'functional',
  },
  {
    workflow_id: 'sales_conversation',
    name: 'Sales Conversation',
    description: 'Drafts replies to inbound messages and escalates sensitive topics to humans.',
    steps: ['supervisor', 'sales_conversation', 'whatsapp', 'crm'],
    implementation_status: 'partial',
  },
  {
    workflow_id: 'followup_automation',
    name: 'Follow-up Automation',
    description: 'Identifies quiet leads and schedules approved follow-ups.',
    steps: ['crm', 'followup', 'email', 'supervisor'],
    implementation_status: 'partial',
  },
  {
    workflow_id: 'crm_sync',
    name: 'CRM Sync',
    description: 'Keeps lead status and activity history in sync with the CRM.',
    steps: ['crm', 'analytics'],
    implementation_status: 'partial',
  },
  {
    workflow_id: 'knowledge_support',
    name: 'Knowledge Support',
    description: 'Answers internal questions from approved, versioned knowledge documents.',
    steps: ['supervisor', 'documents', 'sales_conversation'],
    implementation_status: 'partial',
  },
];

export const DEMO_WORKFLOWS_RESPONSE: WorkflowListResponse = {
  items: DEMO_WORKFLOWS,
  total: DEMO_WORKFLOWS.length,
};

// ---------------------------------------------------------------------------
// Leads
// ---------------------------------------------------------------------------

export const DEMO_LEADS: Lead[] = [
  { id: 'demo-lead-01', name: 'Demo Lead 01', phone: '+971 50 000 0001', email: 'demo.lead01@example.com', source: 'website', score: 86, category: 'hot', status: 'qualified', assignedAgent: 'Property Recommendation Agent', interest: '2BR apartment, waterfront', createdAt: '2026-10-07T06:12:00Z' },
  { id: 'demo-lead-02', name: 'Demo Lead 02', phone: '+971 50 000 0002', email: 'demo.lead02@example.com', source: 'whatsapp', score: 72, category: 'warm', status: 'qualifying', assignedAgent: 'Qualification Agent', interest: 'Townhouse, family community', createdAt: '2026-10-07T09:40:00Z' },
  { id: 'demo-lead-03', name: 'Demo Lead 03', phone: '+971 50 000 0003', email: 'demo.lead03@example.com', source: 'portal_listing', score: 91, category: 'hot', status: 'handed_off', assignedAgent: 'Human broker (demo)', interest: 'Penthouse, ready to move', createdAt: '2026-10-06T14:05:00Z' },
  { id: 'demo-lead-04', name: 'Demo Lead 04', phone: '+971 50 000 0004', email: 'demo.lead04@example.com', source: 'social_ads', score: 38, category: 'cold', status: 'nurturing', assignedAgent: 'Follow-up Agent', interest: 'Studio, investment', createdAt: '2026-10-06T08:22:00Z' },
  { id: 'demo-lead-05', name: 'Demo Lead 05', phone: '+971 50 000 0005', email: 'demo.lead05@example.com', source: 'referral', score: 64, category: 'warm', status: 'qualified', assignedAgent: 'Sales Conversation Agent', interest: '3BR villa, off-plan', createdAt: '2026-10-05T17:48:00Z' },
  { id: 'demo-lead-06', name: 'Demo Lead 06', phone: '+971 50 000 0006', email: 'demo.lead06@example.com', source: 'website', score: 55, category: 'warm', status: 'new', assignedAgent: 'Lead Intake Agent', interest: '1BR apartment', createdAt: '2026-10-08T05:02:00Z' },
  { id: 'demo-lead-07', name: 'Demo Lead 07', phone: '+971 50 000 0007', email: 'demo.lead07@example.com', source: 'whatsapp', score: 22, category: 'cold', status: 'closed_lost', assignedAgent: 'Follow-up Agent', interest: 'Rental enquiry', createdAt: '2026-10-03T11:30:00Z' },
  { id: 'demo-lead-08', name: 'Demo Lead 08', phone: '+971 50 000 0008', email: 'demo.lead08@example.com', source: 'portal_listing', score: 78, category: 'warm', status: 'qualifying', assignedAgent: 'Qualification Agent', interest: '2BR apartment, near metro', createdAt: '2026-10-07T13:15:00Z' },
  { id: 'demo-lead-09', name: 'Demo Lead 09', phone: '+971 50 000 0009', email: 'demo.lead09@example.com', source: 'walk_in', score: 83, category: 'hot', status: 'qualified', assignedAgent: 'Property Recommendation Agent', interest: '4BR villa, golf view', createdAt: '2026-10-04T10:00:00Z' },
  { id: 'demo-lead-10', name: 'Demo Lead 10', phone: '+971 50 000 0010', email: 'demo.lead10@example.com', source: 'social_ads', score: 47, category: 'warm', status: 'nurturing', assignedAgent: 'Follow-up Agent', interest: 'Off-plan payment plans', createdAt: '2026-10-02T15:45:00Z' },
  { id: 'demo-lead-11', name: 'Demo Lead 11', phone: '+971 50 000 0011', email: 'demo.lead11@example.com', source: 'website', score: 69, category: 'warm', status: 'new', assignedAgent: 'Lead Intake Agent', interest: 'Townhouse, 3BR', createdAt: '2026-10-08T06:30:00Z' },
  { id: 'demo-lead-12', name: 'Demo Lead 12', phone: '+971 50 000 0012', email: 'demo.lead12@example.com', source: 'referral', score: 93, category: 'hot', status: 'handed_off', assignedAgent: 'Human broker (demo)', interest: 'Penthouse, sea view', createdAt: '2026-10-01T12:10:00Z' },
];

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export const DEMO_CONVERSATIONS: Conversation[] = [
  {
    id: 'demo-conv-01',
    leadName: 'Demo Lead 01',
    channel: 'whatsapp',
    subject: 'Viewing request — Demo Marina Residences (Fictional)',
    handledBy: 'Sales Conversation Agent',
    lastMessageAt: '2026-10-08T07:42:00Z',
    escalated: false,
    messages: [
      { id: 'm1', sender: 'lead', author: 'Demo Lead 01', text: 'Hi, is the 2BR unit still available for a viewing this weekend?', sentAt: '2026-10-08T07:30:00Z' },
      { id: 'm2', sender: 'agent', author: 'Sales Conversation Agent', text: 'Thanks for reaching out. A broker will confirm viewing slots shortly. Do you prefer Saturday or Sunday?', sentAt: '2026-10-08T07:31:00Z' },
      { id: 'm3', sender: 'lead', author: 'Demo Lead 01', text: 'Saturday morning works best.', sentAt: '2026-10-08T07:42:00Z' },
    ],
  },
  {
    id: 'demo-conv-02',
    leadName: 'Demo Lead 03',
    channel: 'email',
    subject: 'Payment plan question',
    handledBy: 'Human broker (demo)',
    lastMessageAt: '2026-10-07T15:10:00Z',
    escalated: true,
    escalationReason: 'Lead asked for contract terms — requires human review.',
    messages: [
      { id: 'm1', sender: 'lead', author: 'Demo Lead 03', text: 'Could you share the exact contract terms and the refund conditions?', sentAt: '2026-10-07T14:55:00Z' },
      { id: 'm2', sender: 'agent', author: 'Supervisor Agent', text: 'Escalated to a human broker: contractual terms are outside automated scope.', sentAt: '2026-10-07T14:56:00Z' },
      { id: 'm3', sender: 'human', author: 'Broker (demo)', text: 'I will send the official documents after our call tomorrow.', sentAt: '2026-10-07T15:10:00Z' },
    ],
  },
  {
    id: 'demo-conv-03',
    leadName: 'Demo Lead 06',
    channel: 'web',
    subject: 'Website chat — 1BR enquiry',
    handledBy: 'Lead Intake Agent',
    lastMessageAt: '2026-10-08T05:06:00Z',
    escalated: false,
    messages: [
      { id: 'm1', sender: 'lead', author: 'Demo Lead 06', text: 'Looking for a 1BR apartment, budget is flexible.', sentAt: '2026-10-08T05:02:00Z' },
      { id: 'm2', sender: 'agent', author: 'Lead Intake Agent', text: 'Thanks! Could you share your preferred communities and move-in timeline?', sentAt: '2026-10-08T05:03:00Z' },
      { id: 'm3', sender: 'lead', author: 'Demo Lead 06', text: 'Within six months, ideally close to the metro.', sentAt: '2026-10-08T05:06:00Z' },
    ],
  },
  {
    id: 'demo-conv-04',
    leadName: 'Demo Lead 09',
    channel: 'whatsapp',
    subject: 'Villa shortlist follow-up',
    handledBy: 'Property Recommendation Agent',
    lastMessageAt: '2026-10-07T18:20:00Z',
    escalated: true,
    escalationReason: 'Lead requested a price guarantee — pricing commitments need human approval.',
    messages: [
      { id: 'm1', sender: 'agent', author: 'Property Recommendation Agent', text: 'Here is a shortlist of three demo villas matching your preferences.', sentAt: '2026-10-07T18:00:00Z' },
      { id: 'm2', sender: 'lead', author: 'Demo Lead 09', text: 'Can you guarantee the price on the second one until next month?', sentAt: '2026-10-07T18:20:00Z' },
    ],
  },
  {
    id: 'demo-conv-05',
    leadName: 'Demo Lead 10',
    channel: 'email',
    subject: 'Follow-up: off-plan options',
    handledBy: 'Follow-up Agent',
    lastMessageAt: '2026-10-06T09:00:00Z',
    escalated: false,
    messages: [
      { id: 'm1', sender: 'agent', author: 'Follow-up Agent', text: 'Checking in on your interest in off-plan projects. Would a short call this week help?', sentAt: '2026-10-06T09:00:00Z' },
    ],
  },
];

// ---------------------------------------------------------------------------
// Properties (fictional projects; prices are illustrative only)
// ---------------------------------------------------------------------------

export const DEMO_PROPERTIES: PropertyUnit[] = [
  { id: 'demo-unit-01', project: 'Demo Marina Residences (Fictional)', community: 'Marina District (demo)', developer: 'Demo Developer A (Fictional)', unitType: 'Apartment', bedrooms: 2, sizeSqft: 1180, illustrativePriceAed: 1000000, status: 'available', handover: 'Ready' },
  { id: 'demo-unit-02', project: 'Demo Marina Residences (Fictional)', community: 'Marina District (demo)', developer: 'Demo Developer A (Fictional)', unitType: 'Penthouse', bedrooms: 4, sizeSqft: 3900, illustrativePriceAed: 5000000, status: 'reserved', handover: 'Ready' },
  { id: 'demo-unit-03', project: 'Demo Creek Heights (Fictional)', community: 'Creekside (demo)', developer: 'Demo Developer B (Fictional)', unitType: 'Apartment', bedrooms: 1, sizeSqft: 760, illustrativePriceAed: 700000, status: 'off_plan', handover: 'Q4 2027' },
  { id: 'demo-unit-04', project: 'Demo Creek Heights (Fictional)', community: 'Creekside (demo)', developer: 'Demo Developer B (Fictional)', unitType: 'Apartment', bedrooms: 3, sizeSqft: 1650, illustrativePriceAed: 1500000, status: 'off_plan', handover: 'Q4 2027' },
  { id: 'demo-unit-05', project: 'Demo Palm Vista Villas (Fictional)', community: 'Island Crescent (demo)', developer: 'Demo Developer C (Fictional)', unitType: 'Villa', bedrooms: 5, sizeSqft: 6200, illustrativePriceAed: 9000000, status: 'available', handover: 'Ready' },
  { id: 'demo-unit-06', project: 'Demo Downtown Lofts (Fictional)', community: 'City Centre (demo)', developer: 'Demo Developer A (Fictional)', unitType: 'Apartment', bedrooms: 0, sizeSqft: 480, illustrativePriceAed: 500000, status: 'available', handover: 'Ready' },
  { id: 'demo-unit-07', project: 'Demo Hills Townhouses (Fictional)', community: 'Green Hills (demo)', developer: 'Demo Developer C (Fictional)', unitType: 'Townhouse', bedrooms: 3, sizeSqft: 2300, illustrativePriceAed: 2000000, status: 'reserved', handover: 'Q2 2027' },
  { id: 'demo-unit-08', project: 'Demo Hills Townhouses (Fictional)', community: 'Green Hills (demo)', developer: 'Demo Developer C (Fictional)', unitType: 'Townhouse', bedrooms: 4, sizeSqft: 2900, illustrativePriceAed: 2500000, status: 'off_plan', handover: 'Q2 2027' },
];

// ---------------------------------------------------------------------------
// Knowledge documents
// ---------------------------------------------------------------------------

export const DEMO_KNOWLEDGE_DOCUMENTS: KnowledgeDocument[] = [
  { id: 'kb-01', title: 'Demo Brokerage FAQ', category: 'Sales', version: 'v1.4', owner: 'Sales Ops (demo)', updatedAt: '2026-09-28T09:00:00Z', reviewIntervalDays: 90, access: 'public' },
  { id: 'kb-02', title: 'Demo Off-plan Payment Plan Guide', category: 'Sales', version: 'v2.0', owner: 'Sales Ops (demo)', updatedAt: '2026-05-12T09:00:00Z', reviewIntervalDays: 60, access: 'internal' },
  { id: 'kb-03', title: 'Lead Qualification Rubric', category: 'Operations', version: 'v1.1', owner: 'AI Ops (demo)', updatedAt: '2026-09-15T09:00:00Z', reviewIntervalDays: 90, access: 'internal' },
  { id: 'kb-04', title: 'Escalation & Approval Policy', category: 'Compliance', version: 'v3.2', owner: 'Compliance (demo)', updatedAt: '2026-08-30T09:00:00Z', reviewIntervalDays: 30, access: 'restricted' },
  { id: 'kb-05', title: 'Demo Project Fact Sheets (Fictional)', category: 'Inventory', version: 'v0.9', owner: 'Listings (demo)', updatedAt: '2026-06-01T09:00:00Z', reviewIntervalDays: 30, access: 'internal' },
  { id: 'kb-06', title: 'WhatsApp Template Library', category: 'Messaging', version: 'v1.0', owner: 'Marketing (demo)', updatedAt: '2026-10-02T09:00:00Z', reviewIntervalDays: 60, access: 'internal' },
  { id: 'kb-07', title: 'Data Retention Guidelines', category: 'Compliance', version: 'v1.2', owner: 'Compliance (demo)', updatedAt: '2026-03-20T09:00:00Z', reviewIntervalDays: 180, access: 'restricted' },
];

// ---------------------------------------------------------------------------
// Integrations (all placeholders — nothing is connected)
// ---------------------------------------------------------------------------

export const DEMO_INTEGRATIONS: Integration[] = [
  { id: 'espocrm', name: 'EspoCRM', category: 'CRM', mode: 'mock', description: 'Lead, contact and task sync.', note: 'Using in-memory mock adapter. No CRM credentials configured.' },
  { id: 'meta-whatsapp', name: 'Meta WhatsApp Business', category: 'Messaging', mode: 'mock', description: 'Template and session messaging.', note: 'Mock connector only. No messages are sent.' },
  { id: 'google', name: 'Google Workspace', category: 'Email & Calendar', mode: 'not_configured', description: 'Email drafts and viewing calendar.', note: 'OAuth client not configured.' },
  { id: 'bayut', name: 'Bayut', category: 'Listing portal', mode: 'pending_access', description: 'Portal lead ingestion.', note: 'Pending authorized API access. No scraping is performed.' },
  { id: 'property-finder', name: 'Property Finder', category: 'Listing portal', mode: 'pending_access', description: 'Portal lead ingestion.', note: 'Pending authorized API access. No scraping is performed.' },
  { id: 'telephony', name: 'Telephony', category: 'Voice', mode: 'not_configured', description: 'Call handling for the Voice Agent.', note: 'Provider not selected. Voice Agent is interface-only.' },
  { id: 'n8n', name: 'n8n', category: 'Automation', mode: 'mock', description: 'Workflow triggers and webhooks.', note: 'Webhooks point to a mock endpoint.' },
  { id: 'slack', name: 'Slack', category: 'Notifications', mode: 'not_configured', description: 'Approval and escalation alerts.', note: 'Bot token not configured.' },
];

// ---------------------------------------------------------------------------
// Overview + analytics
// ---------------------------------------------------------------------------

export const DEMO_OVERVIEW_KPIS: Kpi[] = [
  { id: 'leads-week', label: 'Leads this week', value: '48', delta: '+12% vs last week', deltaTone: 'positive', trend: [22, 30, 27, 35, 31, 40, 43, 48] },
  { id: 'qualified-rate', label: 'Qualified rate', value: '41.7%', delta: '+3.1 pts', deltaTone: 'positive', trend: [33, 35, 34, 38, 37, 39, 40, 41.7] },
  { id: 'pending-approvals', label: 'Pending approvals', value: '6', delta: '2 older than 4h', deltaTone: 'negative', hint: 'Human-in-the-loop queue' },
  { id: 'active-agents', label: 'Active agents', value: '12 / 13', delta: 'Voice is interface-only', deltaTone: 'neutral' },
];

export const DEMO_LEAD_SOURCES: ChartDatum[] = [
  { label: 'Website', value: 16 },
  { label: 'WhatsApp', value: 12 },
  { label: 'Portals', value: 9 },
  { label: 'Social ads', value: 6 },
  { label: 'Referral', value: 3 },
  { label: 'Walk-in', value: 2 },
];

export const DEMO_PIPELINE_FUNNEL: ChartDatum[] = [
  { label: 'Captured', value: 48 },
  { label: 'Qualified', value: 20 },
  { label: 'Recommended', value: 14 },
  { label: 'Viewing booked', value: 7 },
  { label: 'Handed to broker', value: 4 },
];

export const DEMO_AGENT_ACTIVITY: AgentActivity[] = [
  { id: 'act-01', agentId: 'lead_intake', agentName: 'Lead Intake Agent', action: 'Created lead', subject: 'Demo Lead 11', at: '2026-10-08T06:30:00Z', outcome: 'success' },
  { id: 'act-02', agentId: 'qualification', agentName: 'Qualification Agent', action: 'Scored lead (69)', subject: 'Demo Lead 11', at: '2026-10-08T06:31:00Z', outcome: 'success' },
  { id: 'act-03', agentId: 'sales_conversation', agentName: 'Sales Conversation Agent', action: 'Drafted WhatsApp reply', subject: 'Demo Lead 01', at: '2026-10-08T07:31:00Z', outcome: 'pending_approval' },
  { id: 'act-04', agentId: 'supervisor', agentName: 'Supervisor Agent', action: 'Escalated to broker', subject: 'Demo Lead 09', at: '2026-10-07T18:21:00Z', outcome: 'success' },
  { id: 'act-05', agentId: 'crm', agentName: 'CRM Agent', action: 'Synced status', subject: 'Demo Lead 03', at: '2026-10-07T15:12:00Z', outcome: 'success' },
  { id: 'act-06', agentId: 'email', agentName: 'Email Agent', action: 'Send email (mock)', subject: 'Demo Lead 10', at: '2026-10-06T09:00:00Z', outcome: 'skipped' },
  { id: 'act-07', agentId: 'voice', agentName: 'Voice Agent', action: 'Place call', subject: 'Demo Lead 04', at: '2026-10-06T08:40:00Z', outcome: 'failed' },
];

export const DEMO_WEEKLY_LEADS: ChartDatum[] = [
  { label: 'W34', value: 22 },
  { label: 'W35', value: 30 },
  { label: 'W36', value: 27 },
  { label: 'W37', value: 35 },
  { label: 'W38', value: 31 },
  { label: 'W39', value: 40 },
  { label: 'W40', value: 43 },
  { label: 'W41', value: 48 },
];

export const DEMO_CHANNEL_MIX: ChartDatum[] = [
  { label: 'WhatsApp', value: 46 },
  { label: 'Email', value: 28 },
  { label: 'Web chat', value: 26 },
];

export const DEMO_RESPONSE_TIME_MINUTES: ChartDatum[] = [
  { label: 'Mon', value: 6.2 },
  { label: 'Tue', value: 5.1 },
  { label: 'Wed', value: 4.8 },
  { label: 'Thu', value: 5.5 },
  { label: 'Fri', value: 7.4 },
  { label: 'Sat', value: 3.9 },
  { label: 'Sun', value: 4.2 },
];

export const DEMO_LEAD_CATEGORIES: ChartDatum[] = [
  { label: 'Hot', value: 4 },
  { label: 'Warm', value: 6 },
  { label: 'Cold', value: 2 },
];
