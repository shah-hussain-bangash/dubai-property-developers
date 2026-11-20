import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoLeadForm } from '@/features/leads/DemoLeadForm';
import { parseDemoResult, runDemoLead } from '@/services/demoLeads';

const choices = { budget: '1500000', location: 'Business Bay', bedrooms: 1, timeline: 3, purpose: 'investment' as const };
const identity = '11111111-1111-4111-8111-111111111111';
const success = () => ({ dev_only: true, uses_mock_integrations: true, status: 'succeeded', error: null,
  steps: [{ name: 'qualify', outcome: 'continue' }], result: { is_duplicate: false,
    qualification: { score: { score: 72, category: 'warm', factors: [{ name: 'budget', points: 20, reason: 'Budget supplied' }] }, routing: { queue: 'sales-standard' } },
    crm: { external_id: 'mock-lead-fictional' } } });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
function fetcher(body: unknown = success()) {
  return vi.fn().mockResolvedValueOnce(response({ enabled: true, mock_integrations: true, memory_storage: true }))
    .mockResolvedValueOnce(response(body));
}
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('demo lead transport', () => {
  it('checks capabilities and posts fictional contacts once without credentials or consent', async () => {
    const fetch = fetcher(); vi.stubGlobal('fetch', fetch);
    const result = await runDemoLead(choices, identity, new AbortController().signal);
    expect(result.score).toBe(72);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[0][0]).toContain('/demo-capabilities');
    const options = fetch.mock.calls[1][1];
    expect(options.method).toBe('POST'); expect(options.credentials).toBe('omit'); expect(options.redirect).toBe('error');
    const payload = JSON.parse(options.body);
    expect(payload.email).toBe(`demo-${identity}@example.com`);
    expect(payload.phone).toBeUndefined();
    expect(payload.consent_whatsapp).toBe(false); expect(payload.consent_marketing).toBe(false);
  });
  it('rejects a remote API before any request', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://remote.example.test');
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(runDemoLead(choices, identity, new AbortController().signal)).rejects.toThrow('local API');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('stops before mutation when capabilities are unavailable', async () => {
    const fetch = vi.fn().mockResolvedValue(response({}, false)); vi.stubGlobal('fetch', fetch);
    await expect(runDemoLead(choices, identity, new AbortController().signal)).rejects.toThrow('unavailable');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('stops before mutation when mock storage is not confirmed', async () => {
    const fetch = vi.fn().mockResolvedValue(response({ enabled: true, mock_integrations: true, memory_storage: false })); vi.stubGlobal('fetch', fetch);
    await expect(runDemoLead(choices, identity, new AbortController().signal)).rejects.toThrow('not confirmed');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('does not retry a failed mutation or expose server diagnostics', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ enabled: true, mock_integrations: true, memory_storage: true }))
      .mockRejectedValueOnce(new Error('private-server-diagnostic')); vi.stubGlobal('fetch', fetch);
    await expect(runDemoLead(choices, identity, new AbortController().signal)).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('rejects invalid scenarios before requests', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(runDemoLead({ ...choices, budget: '-1' }, identity, new AbortController().signal)).rejects.toThrow('valid demo');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects responses that claim live integrations', () => {
    expect(() => parseDemoResult({ ...success(), uses_mock_integrations: false })).toThrow();
  });
  it('rejects non-finite scores and real CRM identifiers', () => {
    const first = success(); first.result.qualification.score.score = NaN;
    expect(() => parseDemoResult(first)).toThrow();
    const second = success(); second.result.crm.external_id = 'live-record';
    expect(() => parseDemoResult(second)).toThrow();
  });
  it('handles the actual duplicate shape', () => {
    expect(parseDemoResult({ ...success(), result: { is_duplicate: true, crm: null, qualification: null } }).duplicate).toBe(true);
  });
});

describe('demo lead form', () => {
  it('makes no request until submitted and shows no real-contact inputs', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); render(<DemoLeadForm />);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText('Fictional data only')).toBeVisible();
    expect(screen.queryByLabelText(/email|phone/i)).not.toBeInTheDocument();
  });
  it('shows score, category and routing from the API', async () => {
    vi.stubGlobal('fetch', fetcher()); render(<DemoLeadForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Run demo qualification' }));
    expect(await screen.findByText('Demo qualification complete')).toBeVisible();
    expect(screen.getByText('72 / 100')).toBeVisible(); expect(screen.getByText('warm')).toBeVisible();
    expect(screen.getByText('sales-standard')).toBeVisible(); expect(screen.getByText(/sample table below stays unchanged/)).toBeVisible();
  });
  it('locks the form during processing and prevents double submit', async () => {
    let finish: (value: Response) => void = () => undefined;
    const fetch = vi.fn().mockImplementation(() => new Promise<Response>(resolve => { finish = resolve; })); vi.stubGlobal('fetch', fetch);
    const { container } = render(<DemoLeadForm />);
    fireEvent.submit(container.querySelector('form')!); fireEvent.submit(container.querySelector('form')!);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Maximum budget (AED)')).toBeDisabled();
    finish(response({}, false)); await screen.findByRole('alert');
  });
  it('shows a safe error instead of private diagnostics', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private-secret'))); render(<DemoLeadForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Run demo qualification' }));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-secret');
  });
  it('shows duplicates and lets the user start a new fictional contact', async () => {
    vi.stubGlobal('fetch', fetcher({ ...success(), result: { is_duplicate: true, crm: null, qualification: null } })); render(<DemoLeadForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Run demo qualification' }));
    expect(await screen.findByText('Duplicate demo detected')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'New fictional lead' }));
    await waitFor(() => expect(screen.queryByText('Duplicate demo detected')).not.toBeInTheDocument());
  });
});
