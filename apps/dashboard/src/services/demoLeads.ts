import { getApiBaseUrl, getApiCredentials } from '@/lib/config';

export interface DemoLeadChoices {
  budget: string;
  location: string;
  bedrooms: number;
  timeline: number;
  purpose: 'investment' | 'end_use';
}

export interface DemoLeadResult {
  executionId?: string;
  duplicate: boolean;
  score: number | null;
  category: string | null;
  queue: string | null;
  factors: { name: string; points: number; reason: string }[];
  steps: { name: string; status: string }[];
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

function baseUrl(): string {
  const base = new URL(getApiBaseUrl());
  if (base.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)
      || base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
    throw new Error('The demo form requires a local API address.');
  }
  return base.origin;
}

export function parseDemoResult(body: unknown): DemoLeadResult {
  if (!record(body) || body.dev_only !== true || body.uses_mock_integrations !== true
      || body.status !== 'succeeded' || body.error !== null || !record(body.result)
      || typeof body.result.is_duplicate !== 'boolean' || !Array.isArray(body.steps)) {
    throw new Error('The demo workflow did not return a completed result.');
  }
  const executionId = typeof body.execution_id === 'string' && /^[a-f0-9]{32}$/.test(body.execution_id) ? body.execution_id : undefined;
  if (body.execution_id !== undefined && !executionId) throw new Error('Invalid qualification reference.');
  const steps = body.steps.map((step: unknown) => {
    if (!record(step) || typeof step.name !== 'string' || typeof step.outcome !== 'string') {
      throw new Error('The demo workflow returned an invalid step.');
    }
    return { name: step.name, status: step.outcome };
  });
  if (body.result.is_duplicate) {
    if (body.result.crm !== null || body.result.qualification !== null) {
      throw new Error('The duplicate result was inconsistent.');
    }
    return { executionId, duplicate: true, score: null, category: null, queue: null, factors: [], steps };
  }
  const qualification = body.result.qualification;
  const crm = body.result.crm;
  if (!record(qualification) || !record(qualification.score) || !record(qualification.routing)
      || !record(crm) || typeof crm.external_id !== 'string' || !crm.external_id.startsWith('mock-lead-')) {
    throw new Error('The demo qualification result was incomplete.');
  }
  const score = qualification.score;
  if (typeof score.score !== 'number' || !Number.isFinite(score.score) || score.score < 0 || score.score > 100
      || typeof score.category !== 'string' || !['hot', 'warm', 'cold', 'nurture', 'disqualified'].includes(score.category)
      || typeof qualification.routing.queue !== 'string' || !Array.isArray(score.factors)) {
    throw new Error('The demo qualification result was invalid.');
  }
  const factors = score.factors.map((factor: unknown) => {
    if (!record(factor) || typeof factor.name !== 'string' || typeof factor.reason !== 'string'
        || typeof factor.points !== 'number' || !Number.isFinite(factor.points)) {
      throw new Error('The demo score factors were invalid.');
    }
    return { name: factor.name, reason: factor.reason, points: factor.points };
  });
  return { executionId, duplicate: false, score: score.score, category: score.category, queue: qualification.routing.queue, factors, steps };
}

export async function runDemoLead(choices: DemoLeadChoices, identity: string, signal: AbortSignal): Promise<DemoLeadResult> {
  if (!/^[a-zA-Z0-9-]{16,64}$/.test(identity) || !/^\d{1,10}$/.test(choices.budget)
      || Number(choices.budget) <= 0 || !['Business Bay', 'Dubai Marina', 'Jumeirah Village Circle'].includes(choices.location)
      || !Number.isInteger(choices.bedrooms) || choices.bedrooms < 0 || choices.bedrooms > 5
      || ![1, 3, 6, 12].includes(choices.timeline) || !['investment', 'end_use'].includes(choices.purpose)) {
    throw new Error('Choose valid demo requirements before running the workflow.');
  }
  const base = baseUrl();
  // No cookies, tokens, retry, real contacts, or user-authored message text.
  const request = { credentials: getApiCredentials(), redirect: 'error' as const, cache: 'no-store' as const, signal };
  const capability = await fetch(`${base}/api/v1/leads/demo-capabilities`, request);
  if (!capability.ok) throw new Error('The local demo is unavailable. Start the updated API in demo mode.');
  const enabled: unknown = await capability.json();
  if (!record(enabled) || enabled.enabled !== true || enabled.mock_integrations !== true || enabled.memory_storage !== true) {
    throw new Error('The API has not confirmed that demo processing is available.');
  }
  const response = await fetch(`${base}/api/v1/leads/demo-process`, {
    ...request, method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ full_name: 'Fictional Dashboard Demo', email: `demo-${identity}@example.com`,
      source: 'website', message: 'Fictional demo enquiry: requesting a property viewing.',
      budget_max_aed: choices.budget, preferred_locations: [choices.location], property_types: ['apartment'],
      bedrooms: choices.bedrooms, purpose: choices.purpose, timeline_months: choices.timeline,
      consent_marketing: false, consent_whatsapp: false }),
  });
  if (!response.ok) throw new Error('The workflow could not complete. Check the local API and try again manually.');
  return parseDemoResult(await response.json());
}
