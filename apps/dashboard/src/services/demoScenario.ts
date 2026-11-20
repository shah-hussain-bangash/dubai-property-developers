import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
import { parseDemoResult, type DemoLeadResult } from './demoLeads';
import { parsePropertyDemo, type DemoPropertyResult } from './demoProperties';
import { parseDemoReply, type DemoReply } from './demoConversations';

export interface ScenarioChoices { budget: string; location: string; bedrooms: number }
export interface ScenarioResult { status: 'completed' | 'duplicate' | 'no_matches'; lead: DemoLeadResult; properties: DemoPropertyResult | null; reply: DemoReply | null }
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
export function parseScenario(body: unknown): ScenarioResult {
  if (!record(body) || body.dev_only !== true || body.uses_mock_integrations !== true || body.source !== 'fictional-guided-demo'
      || !['completed', 'duplicate', 'no_matches'].includes(String(body.status))) throw new Error('Invalid demo scenario.');
  const lead = parseDemoResult(body.lead);
  const properties = body.properties === null ? null : parsePropertyDemo(body.properties);
  const reply = body.reply === null ? null : parseDemoReply(body.reply);
  if (body.status === 'duplicate' ? (!lead.duplicate || properties !== null || reply !== null)
      : (lead.duplicate || properties === null || (body.status === 'completed' ? (!properties.matches.length || reply === null) : (properties.matches.length !== 0 || reply !== null)))) {
    throw new Error('Inconsistent demo scenario.');
  }
  return { status: body.status as ScenarioResult['status'], lead, properties, reply };
}
export async function runScenario(choices: ScenarioChoices, identity: string, signal: AbortSignal): Promise<ScenarioResult> {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(identity)
      || !/^\d{1,10}$/.test(choices.budget) || Number(choices.budget) <= 0
      || !['Business Bay', 'Dubai Marina', 'Jumeirah Village Circle'].includes(choices.location)
      || !Number.isInteger(choices.bedrooms) || choices.bedrooms < 0 || choices.bedrooms > 5) throw new Error('Invalid fictional requirements.');
  const base = new URL(getApiBaseUrl());
  if (base.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname) || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('A local demo API is required.');
  const options = { credentials: getApiCredentials(), redirect: 'error' as const, cache: 'no-store' as const, signal };
  const available = await fetch(base.origin + '/api/v1/leads/demo-capabilities', options);
  if (!available.ok) throw new Error('Demo unavailable.');
  const capability: unknown = await available.json();
  if (!record(capability) || capability.enabled !== true || capability.mock_integrations !== true || capability.memory_storage !== true) throw new Error('Demo unavailable.');
  const response = await fetch(base.origin + '/api/v1/workflows/demo-scenario', { ...options, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario_id: identity, ...choices }) });
  if (!response.ok) throw new Error('Demo scenario unavailable.');
  return parseScenario(await response.json());
}
