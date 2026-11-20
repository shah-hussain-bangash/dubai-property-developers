import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoScenarioForm } from '@/features/workflows/DemoScenarioForm';
import { parseScenario, runScenario } from '@/services/demoScenario';

const identity = '3ad09721-5373-42bd-b459-1529426e1731';
const choices = { budget: '2000000', location: 'Business Bay', bedrooms: 2 };
const success = () => ({ dev_only: true, uses_mock_integrations: true, source: 'fictional-guided-demo', status: 'completed',
  lead: { dev_only: true, uses_mock_integrations: true, status: 'succeeded', error: null, steps: [], result: { is_duplicate: false, crm: { external_id: 'mock-lead-1' }, qualification: { score: { score: 89, category: 'hot', factors: [] }, routing: { queue: 'sales-priority' } } } },
  properties: { dev_only: true, uses_mock_integrations: true, status: 'succeeded', output: { contains_demo_data: true, disclaimer: 'Prices must be confirmed. No investment return is guaranteed.', no_match_reason: null as string | null, recommendations: [{ listing: { listing_id: 'demo-1', project_name: 'Demo Creek', community: 'Business Bay', bedrooms: 2, price_aed: '1500000', data_as_of: '2026-10-08', availability: 'available', is_demo: true, source: 'demo-seed' }, score: 0.9, reasons: ['Within budget'], caveats: ['DEMO DATA', 'No return guaranteed'] }] } },
  reply: { dev_only: true, uses_mock_integrations: true, source: 'fictional-sales-demo', status: 'pending_approval', sent: false, requires_approval: true, channel: 'web_chat', needs_human: false, handoff_reason: null, intent: 'schedule_viewing', language: 'en', draft: 'Fictional viewing draft', citations: [] } });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const fetcher = (body: unknown = success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('guided demo', () => {
  it('requires capability and posts only fictional requirements', async () => {
    const fetch = fetcher(); vi.stubGlobal('fetch', fetch);
    expect((await runScenario(choices, identity, new AbortController().signal)).status).toBe('completed');
    expect(fetch.mock.calls[0][0]).toContain('demo-capabilities'); expect(fetch.mock.calls[1][0]).toContain('workflows/demo-scenario');
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ scenario_id: identity, ...choices }); expect(fetch.mock.calls[1][1].credentials).toBe('omit');
  });
  it('blocks remote APIs', async () => { vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://example.test'); const f = vi.fn(); vi.stubGlobal('fetch', f); await expect(runScenario(choices, identity, new AbortController().signal)).rejects.toThrow('local'); expect(f).not.toHaveBeenCalled(); });
  it('blocks invalid criteria before requests', async () => { const f = vi.fn(); vi.stubGlobal('fetch', f); await expect(runScenario({ ...choices, budget: '-1' }, identity, new AbortController().signal)).rejects.toThrow(); expect(f).not.toHaveBeenCalled(); });
  it('stops when capability fails', async () => { const f = vi.fn().mockResolvedValue(response({}, false)); vi.stubGlobal('fetch', f); await expect(runScenario(choices, identity, new AbortController().signal)).rejects.toThrow(); expect(f).toHaveBeenCalledTimes(1); });
  it('never automatically retries', async () => { const f = vi.fn().mockResolvedValueOnce(response(capability)).mockRejectedValueOnce(new Error()); vi.stubGlobal('fetch', f); await expect(runScenario(choices, identity, new AbortController().signal)).rejects.toThrow(); expect(f).toHaveBeenCalledTimes(2); });
  it('rejects sent replies', () => { const b = success(); b.reply.sent = true; expect(() => parseScenario(b)).toThrow(); });
  it('rejects live property sources', () => { const b = success(); b.properties.output.recommendations[0].listing.is_demo = false; expect(() => parseScenario(b)).toThrow(); });
  it('rejects inconsistent duplicate stages', () => { const b = success(); b.status = 'duplicate'; expect(() => parseScenario(b)).toThrow(); });
  it('accepts no matches only with skipped reply', () => { const b = { ...success(), status: 'no_matches', reply: null }; b.properties.output.recommendations = []; b.properties.output.contains_demo_data = false; b.properties.output.no_match_reason = 'No demo match'; expect(parseScenario(b).status).toBe('no_matches'); });
  it('makes no requests on mount', () => { const f = vi.fn(); vi.stubGlobal('fetch', f); render(<DemoScenarioForm />); expect(f).not.toHaveBeenCalled(); });
  it('shows all three stages with unsent draft', async () => { vi.stubGlobal('fetch', fetcher()); render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' })); expect(await screen.findByText('Demo completed — reply awaits review')).toBeVisible(); expect(screen.getByText('Demo Creek')).toBeVisible(); expect(screen.getByText('Fictional viewing draft')).toBeVisible(); expect(screen.queryByRole('button', { name: /^send/i })).toBeNull(); });
  it('locks requirements after submission', async () => { vi.stubGlobal('fetch', fetcher()); render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' })); await screen.findByText('Demo completed — reply awaits review'); expect(screen.getByLabelText('Maximum budget (AED)')).toBeDisabled(); });
  it('new scenario unlocks fields', async () => { vi.stubGlobal('fetch', fetcher()); render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' })); await screen.findByText('Demo completed — reply awaits review'); fireEvent.click(screen.getByRole('button', { name: 'New demo scenario' })); expect(screen.getByLabelText('Maximum budget (AED)')).not.toBeDisabled(); });
  it('retains identity for manual repeat', async () => { const f = vi.fn().mockImplementation(async (url: string) => response(url.includes('capabilities') ? capability : success())); vi.stubGlobal('fetch', f); render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' })); await screen.findByText('Demo completed — reply awaits review'); fireEvent.click(screen.getByRole('button', { name: 'Run same scenario' })); await screen.findByText('Demo completed — reply awaits review'); expect(JSON.parse(f.mock.calls[1][1].body).scenario_id).toBe(JSON.parse(f.mock.calls[3][1].body).scenario_id); });
  it('reports a partial-failure warning', async () => { vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error())); render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' })); expect(await screen.findByRole('alert')).toHaveTextContent('mock lead may already exist'); });
});
