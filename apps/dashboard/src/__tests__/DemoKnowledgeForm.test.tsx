import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoKnowledgeForm } from '@/features/knowledge/DemoKnowledgeForm';
import { askDemoKnowledge, parseDemoKnowledge } from '@/services/demoKnowledge';

const success = () => ({ dev_only: true, uses_mock_integrations: true, source: 'fictional-demo-corpus', status: 'pending_approval',
  output: { needs_human: false, answer: 'Fictional demo passage: confirm terms before quoting.' as string | null, notes: [] as string[],
    citations: [{ document_id: 'demo-org:demo-plan:v1', title: 'Demo Plan (Fictional)', version: 1, excerpt: 'Fictional demo passage.' }] } });
const handoff = () => ({ ...success(), status: 'escalated', output: { needs_human: true, answer: null, notes: ['No sufficiently relevant authorized document found.'], citations: [] } });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const fetcher = (body: unknown = success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
const signal = () => new AbortController().signal;
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('demo knowledge transport', () => {
  it('checks local capability before posting only the trimmed question', async () => {
    const fetch = fetcher(); vi.stubGlobal('fetch', fetch);
    expect((await askDemoKnowledge('  Demo payment plan  ', signal())).citations).toHaveLength(1);
    expect(fetch.mock.calls[0][0]).toContain('/demo-capabilities');
    expect(fetch.mock.calls[1][0]).toContain('/knowledge/demo-answer');
    const options = fetch.mock.calls[1][1];
    expect(options.credentials).toBe('omit'); expect(options.redirect).toBe('error');
    expect(JSON.parse(options.body)).toEqual({ question: 'Demo payment plan' });
  });
  it('rejects a remote API before any request', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://remote.example.test'); const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(askDemoKnowledge('Demo question', signal())).rejects.toThrow('local demo'); expect(fetch).not.toHaveBeenCalled();
  });
  it('does not query when demo mode is unconfirmed', async () => {
    const fetch = vi.fn().mockResolvedValue(response({}, false)); vi.stubGlobal('fetch', fetch);
    await expect(askDemoKnowledge('Demo question', signal())).rejects.toThrow(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('never retries a failed workflow request', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response(capability)).mockRejectedValueOnce(new Error('failure')); vi.stubGlobal('fetch', fetch);
    await expect(askDemoKnowledge('Demo question', signal())).rejects.toThrow(); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('rejects empty or oversized questions before requests', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    for (const question of ['  ', 'x'.repeat(1001)]) await expect(askDemoKnowledge(question, signal())).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects an uncited draft', () => {
    const body = success(); body.output.citations = [];
    expect(() => parseDemoKnowledge(body)).toThrow();
  });
  it('requires status and human-handoff flag to agree', () => {
    const body = success(); body.output.needs_human = true;
    expect(() => parseDemoKnowledge(body)).toThrow();
    expect(parseDemoKnowledge(handoff()).needsHuman).toBe(true);
  });
  it('rejects live source claims or malformed citations', () => {
    const body = success(); body.source = 'live-documents';
    expect(() => parseDemoKnowledge(body)).toThrow();
    const invalid = success(); invalid.output.citations[0].title = 'Private document';
    expect(() => parseDemoKnowledge(invalid)).toThrow();
  });
});
describe('demo knowledge panel', () => {
  it('makes no requests on mount', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); render(<DemoKnowledgeForm />);
    expect(fetch).not.toHaveBeenCalled(); expect(screen.getByText('Public fictional documents only')).toBeVisible();
  });
  it('displays a draft with quoted source text and human-review notice', async () => {
    const body = success(); body.output.citations[0].excerpt = '<script>unsafe()</script>';
    vi.stubGlobal('fetch', fetcher(body)); const { container } = render(<DemoKnowledgeForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Ask demo question' }));
    expect(await screen.findByText('Draft answer — review before sharing')).toBeVisible();
    expect(screen.getByText('Demo Plan (Fictional)')).toBeVisible();
    expect(screen.getByText('<script>unsafe()</script>')).toBeVisible();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(/not a sent message/)).toBeVisible();
  });
  it('shows a human handoff without a fabricated answer', async () => {
    vi.stubGlobal('fetch', fetcher(handoff())); render(<DemoKnowledgeForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Ask demo question' }));
    expect(await screen.findByText('Human handoff needed')).toBeVisible();
    expect(screen.queryByText('Cited fictional sources')).not.toBeInTheDocument();
  });
  it('example buttons change the question without submitting', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); render(<DemoKnowledgeForm />);
    fireEvent.click(screen.getByRole('button', { name: 'No-answer example' }));
    expect(screen.getByLabelText('Question about demo documents')).toHaveValue('zzqx unrelated vocabulary');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not display private error details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private-value'))); render(<DemoKnowledgeForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Ask demo question' }));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-value');
  });
  it('locks the form while working and prevents double submit', async () => {
    let finish: (value: Response) => void = () => undefined;
    const fetch = vi.fn().mockImplementation(() => new Promise<Response>(resolve => { finish = resolve; })); vi.stubGlobal('fetch', fetch);
    const { container } = render(<DemoKnowledgeForm />);
    fireEvent.submit(container.querySelector('form')!); fireEvent.submit(container.querySelector('form')!);
    expect(fetch).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('Question about demo documents')).toBeDisabled();
    finish(response({}, false)); await screen.findByRole('alert');
  });
  it('aborts on unmount', () => {
    const fetch = vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    })); vi.stubGlobal('fetch', fetch);
    const { unmount } = render(<DemoKnowledgeForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Ask demo question' }));
    const requestSignal = fetch.mock.calls[0][1].signal as AbortSignal; unmount(); expect(requestSignal.aborted).toBe(true);
  });
});
