import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LocalAiPanel } from '@/features/conversations/LocalAiPanel';
import { generateLocalDraft, parseLocalDraft } from '@/services/localAi';
const success = () => ({ provider:'ollama', model:'qwen3:8b', is_mock:false, sent:false, requires_review:true, text:'Ask about the fictional buyer budget.', input_tokens:40, output_tokens:12 });
const capability = { enabled:true, provider:'ollama', model:'qwen3:8b', sends_messages:false };
const response = (body:unknown, ok=true) => ({ ok, json: async () => body } as Response);
const fetcher = (body:unknown=success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });
describe('real local AI', () => {
  it('does not generate on mount and clearly labels the local model', () => {
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<LocalAiPanel />);
    expect(fetch).not.toHaveBeenCalled();expect(screen.getByText('Try real local AI')).toBeVisible();
    expect(screen.getByText(/No paid API is used/)).toBeVisible();
  });
  it('checks local capability then posts only the trimmed message without credentials', async () => {
    const fetch=fetcher();vi.stubGlobal('fetch',fetch);
    await generateLocalDraft('  Fictional buyer enquiry  ',new AbortController().signal);
    expect(fetch.mock.calls[0][0]).toContain('/local-ai/capabilities');
    expect(fetch.mock.calls[1][0]).toContain('/local-ai/draft');
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({message:'Fictional buyer enquiry'});
    expect(fetch.mock.calls[1][1].credentials).toBe('omit');expect(fetch.mock.calls[1][1].redirect).toBe('error');
  });
  it('rejects remote API settings before any request', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL','https://example.com');const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
    await expect(generateLocalDraft('Fictional enquiry',new AbortController().signal)).rejects.toThrow('local');expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects blank or oversized enquiries before any request', async () => {
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
    for(const message of [' ','x'.repeat(1001)]) await expect(generateLocalDraft(message,new AbortController().signal)).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('stops when local generation is disabled and never retries', async () => {
    const fetch=vi.fn().mockResolvedValue(response({},false));vi.stubGlobal('fetch',fetch);
    await expect(generateLocalDraft('Fictional enquiry',new AbortController().signal)).rejects.toThrow();expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('refuses mock, sent, unreviewed or incorrectly attributed responses', () => {
    for(const change of [{is_mock:true},{sent:true},{requires_review:false},{provider:'openai'},{model:'qwen3:8b-cloud'},{input_tokens:-1},{text:''}]) expect(()=>parseLocalDraft({...success(),...change})).toThrow();
  });
  it('shows real text as plain text and never offers send', async () => {
    vi.stubGlobal('fetch',fetcher({...success(),text:'<script>unsafe()</script>'}));const {container}=render(<LocalAiPanel />);
    fireEvent.click(screen.getByRole('button',{name:'Generate local AI draft'}));
    expect(await screen.findByText('Local AI draft · review required')).toBeVisible();expect(screen.getByText('<script>unsafe()</script>')).toBeVisible();
    expect(container.querySelector('script')).toBeNull();expect(screen.queryByRole('button',{name:/^send/i})).toBeNull();
  });
  it('clears outdated results when the enquiry changes', async () => {
    vi.stubGlobal('fetch',fetcher());render(<LocalAiPanel />);fireEvent.click(screen.getByRole('button',{name:'Generate local AI draft'}));
    await screen.findByText('Local AI draft · review required');fireEvent.change(screen.getByLabelText('Fictional enquiry for local AI'),{target:{value:'Different fictional enquiry'}});
    expect(screen.queryByText('Local AI draft · review required')).toBeNull();
  });
  it('locks inputs and prevents duplicate submission while generating', async () => {
    const fetch=vi.fn().mockReturnValue(new Promise(()=>{}));vi.stubGlobal('fetch',fetch);render(<LocalAiPanel />);
    fireEvent.click(screen.getByRole('button',{name:'Generate local AI draft'}));fireEvent.submit(screen.getByLabelText('Fictional enquiry for local AI').closest('form')!);
    expect(fetch).toHaveBeenCalledTimes(1);expect(screen.getByLabelText('Fictional enquiry for local AI')).toBeDisabled();
  });
  it('sanitizes failures and lets the user clear the enquiry', async () => {
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('private-value')));render(<LocalAiPanel />);fireEvent.click(screen.getByRole('button',{name:'Generate local AI draft'}));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-value');fireEvent.click(screen.getByRole('button',{name:'Clear local AI draft'}));
    expect(screen.getByLabelText('Fictional enquiry for local AI')).toHaveValue('');expect(screen.queryByRole('alert')).toBeNull();
  });
});
