import { getApiBaseUrl, getApiCredentials } from '@/lib/config';
export interface LocalDraft { text: string; input_tokens: number; output_tokens: number }
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
export function parseLocalDraft(body: unknown): LocalDraft {
  if (!record(body) || body.provider !== 'ollama' || body.model !== 'qwen3:8b' || body.is_mock !== false
      || body.sent !== false || body.requires_review !== true || typeof body.text !== 'string' || !body.text.trim()
      || body.text.length > 20000 || !Number.isSafeInteger(body.input_tokens) || Number(body.input_tokens) < 0
      || !Number.isSafeInteger(body.output_tokens) || Number(body.output_tokens) < 0) throw new Error('Local AI response unavailable.');
  return { text: body.text, input_tokens: Number(body.input_tokens), output_tokens: Number(body.output_tokens) };
}
export async function generateLocalDraft(message: string, signal: AbortSignal): Promise<LocalDraft> {
  const text = message.trim();
  if (text.length < 3 || text.length > 1000) throw new Error('Enter between 3 and 1000 characters.');
  const base = new URL(getApiBaseUrl());
  if (base.protocol !== 'http:' || !['localhost','127.0.0.1','[::1]'].includes(base.hostname) || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('A local API is required.');
  const options = { credentials: getApiCredentials(), redirect: 'error' as const, cache: 'no-store' as const, signal };
  const available = await fetch(base.origin + '/api/v1/local-ai/capabilities', options);
  if (!available.ok) throw new Error('Local AI is unavailable.');
  const cap: unknown = await available.json();
  if (!record(cap) || cap.enabled !== true || cap.provider !== 'ollama' || cap.model !== 'qwen3:8b' || cap.sends_messages !== false) throw new Error('Local AI is unavailable.');
  const response = await fetch(base.origin + '/api/v1/local-ai/draft', { ...options, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }) });
  if (!response.ok) throw new Error('Local AI could not finish.');
  return parseLocalDraft(await response.json());
}
