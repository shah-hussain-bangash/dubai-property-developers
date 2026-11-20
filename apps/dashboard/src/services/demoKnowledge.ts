import { getApiBaseUrl, getApiCredentials } from '@/lib/config';

export interface DemoCitation { id: string; title: string; version: number; excerpt: string }
export interface DemoKnowledgeResult { answer: string | null; needsHuman: boolean; citations: DemoCitation[]; notes: string[] }
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export function parseDemoKnowledge(body: unknown): DemoKnowledgeResult {
  if (!record(body) || body.dev_only !== true || body.uses_mock_integrations !== true
      || body.source !== 'fictional-demo-corpus' || !['pending_approval', 'escalated'].includes(String(body.status))
      || !record(body.output) || typeof body.output.needs_human !== 'boolean'
      || body.output.needs_human !== (body.status === 'escalated') || !Array.isArray(body.output.citations)
      || body.output.citations.length > 3 || !Array.isArray(body.output.notes)
      || !body.output.notes.every(note => typeof note === 'string')
      || !(body.output.answer === null || typeof body.output.answer === 'string')) {
    throw new Error('Invalid demo knowledge result.');
  }
  const citations = body.output.citations.map((value: unknown): DemoCitation => {
    if (!record(value) || typeof value.document_id !== 'string' || typeof value.title !== 'string'
        || !value.title.includes('(Fictional)') || typeof value.excerpt !== 'string' || !value.excerpt.trim()
        || typeof value.version !== 'number' || !Number.isInteger(value.version) || value.version < 1) {
      throw new Error('Invalid fictional source citation.');
    }
    return { id: value.document_id, title: value.title, excerpt: value.excerpt, version: value.version };
  });
  const answer = body.output.answer as string | null;
  if ((!body.output.needs_human && (!answer?.trim() || citations.length === 0))
      || (answer && citations.length === 0)) throw new Error('The demo answer requires a source.');
  return { answer, needsHuman: body.output.needs_human, citations, notes: body.output.notes as string[] };
}

export async function askDemoKnowledge(question: string, signal: AbortSignal): Promise<DemoKnowledgeResult> {
  const text = question.trim();
  if (text.length < 3 || text.length > 1000) throw new Error('Enter a demo question between 3 and 1000 characters.');
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
  const response = await fetch(base.origin + '/api/v1/knowledge/demo-answer', {
    ...request, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text }),
  });
  if (!response.ok) throw new Error('The demo knowledge workflow could not complete.');
  return parseDemoKnowledge(await response.json());
}
