import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoScenarioForm } from '@/features/workflows/DemoScenarioForm';
import { buildScenarioReport, downloadScenarioReport } from '@/services/demoScenarioReport';
import { parseScenario } from '@/services/demoScenario';

const choices = { budget: '2000000', location: 'Business Bay', bedrooms: 2 };
const success = () => ({ dev_only: true, uses_mock_integrations: true, source: 'fictional-guided-demo', status: 'completed',
  lead: { dev_only: true, uses_mock_integrations: true, status: 'succeeded', error: null, steps: [], result: { is_duplicate: false, crm: { external_id: 'mock-lead-1' }, qualification: { score: { score: 89, category: 'hot', factors: [] }, routing: { queue: 'sales-priority' } } } },
  properties: { dev_only: true, uses_mock_integrations: true, status: 'succeeded', output: { contains_demo_data: true, disclaimer: 'Prices must be confirmed. No investment return is guaranteed.', no_match_reason: null as string | null, recommendations: [{ listing: { listing_id: 'demo-1', project_name: 'Demo Creek', community: 'Business Bay', bedrooms: 2, price_aed: '1500000', data_as_of: '2026-10-08', availability: 'available', is_demo: true, source: 'demo-seed' }, score: 0.9, reasons: ['Within budget'], caveats: ['DEMO DATA', 'No return guaranteed'] }] } },
  reply: { dev_only: true, uses_mock_integrations: true, source: 'fictional-sales-demo', status: 'pending_approval', sent: false, requires_approval: true, channel: 'web_chat', needs_human: false, handoff_reason: null, intent: 'schedule_viewing', language: 'en', draft: 'Fictional viewing draft', citations: [] } });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const fetcher = (body: unknown = success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('local fictional report', () => {
  it('includes requirements and explicit fictional labels', () => {
    const report = buildScenarioReport(choices, parseScenario(success()), new Date('2026-10-23T00:00:00Z'));
    expect(report.fictional_data).toBe(true); expect(report.mock_integrations).toBe(true);
    expect(report.created_at).toBe('2026-10-23T00:00:00.000Z'); expect(report.requirements.budget_max_aed).toBe('2000000');
  });
  it('preserves source dates, caveats and reasons', () => {
    const report = buildScenarioReport(choices, parseScenario(success()));
    expect(report.property_matching?.matches[0]).toMatchObject({ source: 'demo-seed', data_as_of: '2026-10-08', reasons: ['Within budget'], caveats: ['DEMO DATA', 'No return guaranteed'] });
    expect(report.property_matching?.disclaimer).toContain('must be confirmed');
  });
  it('keeps unknown prices unknown', () => {
    const result = parseScenario(success()); result.properties!.matches[0].price = null; result.properties!.matches[0].caveats.push('Price not confirmed');
    expect(buildScenarioReport(choices, result).property_matching?.matches[0].price_aed).toBeNull();
  });
  it('marks reply unsent and human review required', () => {
    const report = buildScenarioReport(choices, parseScenario(success()));
    expect(report.viewing_reply).toMatchObject({ sent: false, appointment_booked: false, requires_human_review: true });
    expect(report.notice).toContain('No message was sent'); expect(report.notice).toContain('No investment return');
  });
  it('does not export contact, record or execution identifiers', () => {
    const result = { ...parseScenario(success()), email: 'private@example.test', execution_id: 'secret-run', token: 'secret-token' };
    const text = JSON.stringify(buildScenarioReport(choices, result));
    for (const field of ['private@example.test', 'secret-run', 'secret-token', 'mock-lead-1', 'listing_id', 'document_id']) expect(text).not.toContain(field);
  });
  it('preserves duplicate outcome with skipped stages', () => {
    const result = parseScenario(success()); result.status = 'duplicate'; result.lead = { ...result.lead, duplicate: true, score: null, category: null, queue: null }; result.properties = null; result.reply = null;
    const report = buildScenarioReport(choices, result); expect(report.outcome).toBe('duplicate'); expect(report.property_matching).toBeNull(); expect(report.viewing_reply).toBeNull();
  });
  it('preserves no-match explanation without a draft', () => {
    const result = parseScenario(success()); result.status = 'no_matches'; result.properties!.matches = []; result.properties!.noMatch = 'No fictional matches'; result.reply = null;
    expect(buildScenarioReport(choices, result).property_matching?.no_match_reason).toBe('No fictional matches');
  });
  it('downloads JSON locally and releases its object URL', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    const create = vi.fn().mockReturnValue('blob:demo-report'); const revoke = vi.fn();
    vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
    let download = ''; const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { download = this.download; });
    downloadScenarioReport(choices, parseScenario(success()));
    expect(create.mock.calls[0][0].type).toBe('application/json;charset=utf-8'); expect(click).toHaveBeenCalledOnce(); expect(download).toBe('fictional-workflow-demo.json'); expect(revoke).toHaveBeenCalledWith('blob:demo-report'); expect(document.querySelector('a[download]')).toBeNull(); expect(fetch).not.toHaveBeenCalled();
  });
  it('cleans up even if browser download fails', () => {
    const revoke = vi.fn(); vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn().mockReturnValue('blob:failed'); static revokeObjectURL = revoke; });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw new Error('failure'); });
    expect(() => downloadScenarioReport(choices, parseScenario(success()))).toThrow(); expect(revoke).toHaveBeenCalledWith('blob:failed'); expect(document.querySelector('a[download]')).toBeNull();
  });
  it('shows no download button before a result', () => { render(<DemoScenarioForm />); expect(screen.queryByRole('button', { name: 'Download demo report' })).toBeNull(); });
  it('downloads the displayed result without another API call', async () => {
    const fetch = fetcher(); vi.stubGlobal('fetch', fetch);
    vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn().mockReturnValue('blob:demo'); static revokeObjectURL = vi.fn(); });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Download demo report' }));
    expect(click).toHaveBeenCalledOnce(); expect(fetch).toHaveBeenCalledTimes(2); expect(screen.getByText(/Demo report prepared for download/)).toBeVisible();
  });
  it('clears the report and notice when starting a new scenario', async () => {
    vi.stubGlobal('fetch', fetcher()); render(<DemoScenarioForm />); fireEvent.click(screen.getByRole('button', { name: 'Run guided demo' })); await screen.findByRole('button', { name: 'Download demo report' });
    fireEvent.click(screen.getByRole('button', { name: 'New demo scenario' })); expect(screen.queryByRole('button', { name: 'Download demo report' })).toBeNull();
  });
});
