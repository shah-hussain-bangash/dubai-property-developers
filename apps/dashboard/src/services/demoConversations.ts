import { getApiBaseUrl, getApiCredentials } from '@/lib/config';

export interface ReplyCitation { id: string; title: string; version: number; excerpt: string }
export interface DemoReply { text: string; intent: string; language: 'en' | 'ar'; needsHuman: boolean; reason: string | null; citations: ReplyCitation[] }
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const intents = ['property_enquiry', 'pricing', 'payment_plan', 'schedule_viewing', 'callback_request', 'complaint', 'unsubscribe', 'general', 'unknown'];

export function parseDemoReply(body: unknown): DemoReply {
  if (!record(body) || body.dev_only !== true || body.uses_mock_integrations !== true
      || body.source !== 'fictional-sales-demo' || body.sent !== false || body.requires_approval !== true
      || body.channel !== 'web_chat' || !['pending_approval', 'escalated'].includes(String(body.status))
      || typeof body.needs_human !== 'boolean' || body.needs_human !== (body.status === 'escalated')
      || typeof body.draft !== 'string' || !body.draft.trim()
      || typeof body.intent !== 'string' || !intents.includes(body.intent)
      || !['en', 'ar'].includes(String(body.language)) || !Array.isArray(body.citations) || body.citations.length > 3
      || !(body.handoff_reason === null || typeof body.handoff_reason === 'string')
      || (body.needs_human && (typeof body.handoff_reason !== 'string' || !body.handoff_reason))) {
    throw new Error('Invalid unsent demo reply.');
  }
  const citations = body.citations.map((value: unknown): ReplyCitation => {
    if (!record(value) || typeof value.document_id !== 'string' || typeof value.title !== 'string'
        || !value.title.includes('(Fictional)') || typeof value.excerpt !== 'string' || !value.excerpt.trim()
        || typeof value.version !== 'number' || !Number.isInteger(value.version) || value.version < 1) {
      throw new Error('Invalid fictional reply citation.');
    }
    return { id: value.document_id, title: value.title, excerpt: value.excerpt, version: value.version };
  });
  if (body.intent === 'payment_plan' && !body.needs_human && citations.length === 0) throw new Error('A payment-plan reply requires cited demo documents.');
  return { text: body.draft, intent: body.intent, language: body.language as 'en' | 'ar', needsHuman: body.needs_human,
    reason: body.handoff_reason as string | null, citations };
}

export async function prepareDemoReply(message: string, signal: AbortSignal): Promise<DemoReply> {
  const text = message.trim();
  if (text.length < 3 || text.length > 4096) throw new Error('Enter a fictional message between 3 and 4096 characters.');
  const base = new URL(getApiBaseUrl());
  if (base.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)
      || base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
    throw new Error('A local demo API is required.');
  }
  const request = { credentials: getApiCredentials(), redirect: 'error' as const, cache: 'no-store' as const, signal };
  const available = await fetch(base.origin + '/api/v1/leads/demo-capabilities', request);
  if (!available.ok) throw new Error('The local demo is unavailable.');
  const capability: unknown = await available.json();
  if (!record(capability) || capability.enabled !== true || capability.mock_integrations !== true || capability.memory_storage !== true) {
    throw new Error('The local demo environment could not be confirmed.');
  }
  const response = await fetch(base.origin + '/api/v1/conversations/demo-draft', {
    ...request, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }),
  });
  if (!response.ok) throw new Error('The demo reply could not be prepared.');
  return parseDemoReply(await response.json());
}
