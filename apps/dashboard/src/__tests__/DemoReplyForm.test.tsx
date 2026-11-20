import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoReplyForm } from '@/features/conversations/DemoReplyForm';
import { parseDemoReply, prepareDemoReply } from '@/services/demoConversations';

const success = () => ({ dev_only: true, uses_mock_integrations: true, source: 'fictional-sales-demo', status: 'pending_approval',
  sent: false, requires_approval: true, channel: 'web_chat', needs_human: false, handoff_reason: null as string | null,
  intent: 'payment_plan', language: 'en', draft: 'Fictional payment-plan draft. Confirm terms before quoting.',
  citations: [{ document_id: 'demo-org:demo-plan:v1', title: 'Demo Plan (Fictional)', version: 1, excerpt: 'Fictional source passage.' }] });
const handoff = () => ({ ...success(), status: 'escalated', needs_human: true, intent: 'complaint',
  handoff_reason: 'A complaint needs a staff member.', draft: 'Fictional acknowledgement draft.', citations: [] });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const fetcher = (body: unknown = success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
const signal = () => new AbortController().signal;
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('demo sales reply transport', () => {
  it('checks capability before posting only the trimmed fictional message', async () => {
    const fetch = fetcher(); vi.stubGlobal('fetch', fetch);
    expect((await prepareDemoReply('  Demo payment plan  ', signal())).citations).toHaveLength(1);
    expect(fetch.mock.calls[0][0]).toContain('/demo-capabilities');
    expect(fetch.mock.calls[1][0]).toContain('/conversations/demo-draft');
    const options = fetch.mock.calls[1][1];
    expect(options.credentials).toBe('omit'); expect(options.redirect).toBe('error');
    expect(JSON.parse(options.body)).toEqual({ message: 'Demo payment plan' });
  });
  it('rejects remote APIs before any request', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://remote.example.test'); const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(prepareDemoReply('Demo message', signal())).rejects.toThrow('local demo'); expect(fetch).not.toHaveBeenCalled();
  });
  it('does not query when demo mode is unconfirmed', async () => {
    const fetch = vi.fn().mockResolvedValue(response({}, false)); vi.stubGlobal('fetch', fetch);
    await expect(prepareDemoReply('Demo message', signal())).rejects.toThrow(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('never retries a failed draft request', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response(capability)).mockRejectedValueOnce(new Error('failure')); vi.stubGlobal('fetch', fetch);
    await expect(prepareDemoReply('Demo message', signal())).rejects.toThrow(); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('rejects blank and oversized messages before requests', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    for (const message of ['  ', 'x'.repeat(4097)]) await expect(prepareDemoReply(message, signal())).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects sent replies or a different channel', () => {
    const sent = success(); sent.sent = true; expect(() => parseDemoReply(sent)).toThrow();
    const channel = success(); channel.channel = 'whatsapp'; expect(() => parseDemoReply(channel)).toThrow();
  });
  it('requires review and citations for payment-plan answers', () => {
    const body = success(); body.requires_approval = false; expect(() => parseDemoReply(body)).toThrow();
    const uncited = success(); uncited.citations = []; expect(() => parseDemoReply(uncited)).toThrow();
  });
  it('requires a handoff reason and consistent status', () => {
    expect(parseDemoReply(handoff()).needsHuman).toBe(true);
    const invalid = success(); invalid.needs_human = true; expect(() => parseDemoReply(invalid)).toThrow();
  });
});
describe('demo sales reply panel', () => {
  it('makes no requests on mount', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); render(<DemoReplyForm />);
    expect(fetch).not.toHaveBeenCalled(); expect(screen.getByText('Draft only · nothing is sent')).toBeVisible();
  });
  it('shows an unsent cited draft and escapes returned markup', async () => {
    const body = success(); body.draft = '<script>unsafe()</script>';
    vi.stubGlobal('fetch', fetcher(body)); const { container } = render(<DemoReplyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare demo reply' }));
    expect(await screen.findByText('Draft ready for human review')).toBeVisible();
    expect(screen.getByText('Demo Plan (Fictional)')).toBeVisible();
    expect(screen.getByText('<script>unsafe()</script>')).toBeVisible(); expect(container.querySelector('script')).toBeNull();
    expect(screen.queryByRole('button', { name: /^send/i })).not.toBeInTheDocument();
  });
  it('shows staff handoff and labels its acknowledgement as unsent', async () => {
    vi.stubGlobal('fetch', fetcher(handoff())); render(<DemoReplyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare demo reply' }));
    expect(await screen.findByText('Staff handoff required')).toBeVisible();
    expect(screen.getByText('Unsent acknowledgement draft')).toBeVisible();
    expect(screen.getByText('A complaint needs a staff member.')).toBeVisible();
  });
  it('example buttons prefill without submitting', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); render(<DemoReplyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Complaint example' }));
    expect(screen.getByLabelText('Message from a fictional customer')).toHaveValue('This is a complaint about my booking');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not expose private diagnostics in errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private-value'))); render(<DemoReplyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare demo reply' }));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-value');
  });
  it('locks the form during processing and prevents double submit', async () => {
    let finish: (value: Response) => void = () => undefined;
    const fetch = vi.fn().mockImplementation(() => new Promise<Response>(resolve => { finish = resolve; })); vi.stubGlobal('fetch', fetch);
    const { container } = render(<DemoReplyForm />);
    fireEvent.submit(container.querySelector('form')!); fireEvent.submit(container.querySelector('form')!);
    expect(fetch).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('Message from a fictional customer')).toBeDisabled();
    finish(response({}, false)); await screen.findByRole('alert');
  });
  it('aborts on unmount', () => {
    const fetch = vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    })); vi.stubGlobal('fetch', fetch);
    const { unmount } = render(<DemoReplyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare demo reply' }));
    const requestSignal = fetch.mock.calls[0][1].signal as AbortSignal; unmount(); expect(requestSignal.aborted).toBe(true);
  });
});
