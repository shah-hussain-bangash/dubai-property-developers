import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
export interface LocalSource { label: string; document_id: string; title: string; version: number; excerpt: string }
export type LocalKnowledge = { generated: false; reason: string } | { generated: true; text: string; sources: LocalSource[]; confirmation: string };
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
export function parseLocalKnowledge(body: unknown): LocalKnowledge {
  if (!record(body) || body.sent !== false || body.requires_review !== true || !Array.isArray(body.sources)) throw new Error('Local knowledge response unavailable.');
  if (body.generated === false) {
    if (typeof body.reason !== 'string' || !body.reason.trim() || body.sources.length !== 0) throw new Error('Invalid staff handoff.');
    return { generated: false, reason: body.reason };
  }
  if (body.generated !== true || body.provider !== 'ollama' || body.model !== 'qwen3:8b' || body.is_mock !== false || typeof body.text !== 'string' || !body.text.trim() || body.text.length > 20000 || body.sources.length < 1 || body.sources.length > 3 || typeof body.confirmation !== 'string' || !body.confirmation.trim()) throw new Error('Invalid generated knowledge draft.');
  const sources = body.sources.map((source: unknown, index: number): LocalSource => {
    if (!record(source) || source.label !== `S${index+1}` || typeof source.document_id !== 'string' || typeof source.title !== 'string' || !source.title.includes('(Fictional)') || !Number.isSafeInteger(source.version) || Number(source.version) < 1 || typeof source.excerpt !== 'string' || !source.excerpt.trim()) throw new Error('Invalid fictional source.');
    return { label: source.label as string, document_id: source.document_id, title: source.title, version: Number(source.version), excerpt: source.excerpt };
  });
  const labels = [...body.text.matchAll(/\[S(\d+)\]/g)].map(match => `S${match[1]}`);
  if (!labels.length || labels.some(label => !sources.some(source => source.label === label))) throw new Error('Invalid source label.');
  return { generated: true, text: body.text, sources, confirmation: body.confirmation };
}
export async function askLocalKnowledge(question: string, signal: AbortSignal): Promise<LocalKnowledge> {
  const text=question.trim();
  if (text.length < 3 || text.length > 1000) throw new Error('Enter a fictional question between 3 and 1000 characters.');
  const base=new URL(getApiBaseUrl());
  if (base.protocol !== 'http:' || !['localhost','127.0.0.1','[::1]'].includes(base.hostname) || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('A local API is required.');
  const options={ credentials:getApiCredentials(), redirect:'error' as const, cache:'no-store' as const, signal };
  const response=await fetch(base.origin+'/api/v1/local-ai/knowledge-draft',{...options,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text})});
  if (!response.ok) throw new Error('Local knowledge drafting unavailable.');
  return parseLocalKnowledge(await response.json());
}
