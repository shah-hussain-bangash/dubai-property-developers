import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoPropertyForm } from '@/features/properties/DemoPropertyForm';
import { matchDemoProperties, parsePropertyDemo } from '@/services/demoProperties';

const choices = { budget: '2000000', location: 'any', bedrooms: 'any', paymentPlan: false };
const disclaimer = 'Prices must be confirmed with the developer. No investment return is implied or guaranteed.';
const success = () => ({ dev_only: true, uses_mock_integrations: true, status: 'succeeded', output: {
  contains_demo_data: true, no_match_reason: null as string | null, disclaimer,
  recommendations: [{ score: 0.8, reasons: ['Matches demo criteria'], caveats: ['DEMO DATA: fictional listing.', 'No return is guaranteed.'],
    listing: { is_demo: true, source: 'demo-seed', listing_id: 'DEMO-001', project_name: 'Fictional Test Project',
      community: 'Dubai Marina', bedrooms: 1, price_aed: '1450000' as string | null, data_as_of: '2026-01-01', availability: 'available' } }] } });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const fetcher = (body: unknown = success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
const signal = () => new AbortController().signal;
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('fictional property transport', () => {
  it('checks the demo environment before posting criteria without credentials', async () => {
    const fetch = fetcher(); vi.stubGlobal('fetch', fetch);
    expect((await matchDemoProperties(choices, signal())).matches).toHaveLength(1);
    expect(fetch.mock.calls[0][0]).toContain('/demo-capabilities');
    expect(fetch.mock.calls[1][0]).toContain('/properties/demo-recommendations');
    const options = fetch.mock.calls[1][1];
    expect(options.credentials).toBe('omit'); expect(options.redirect).toBe('error'); expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toMatchObject({ budget_max_aed: '2000000', limit: 3, include_unavailable: false });
  });
  it('rejects remote API addresses before a request', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://remote.example.test'); const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(matchDemoProperties(choices, signal())).rejects.toThrow('local demo');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not post when demo capability is unavailable', async () => {
    const fetch = vi.fn().mockResolvedValue(response({}, false)); vi.stubGlobal('fetch', fetch);
    await expect(matchDemoProperties(choices, signal())).rejects.toThrow(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('does not retry a failed workflow', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response(capability)).mockRejectedValueOnce(new Error('failed')); vi.stubGlobal('fetch', fetch);
    await expect(matchDemoProperties(choices, signal())).rejects.toThrow(); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('rejects invalid budgets before requests', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(matchDemoProperties({ ...choices, budget: '-1' }, signal())).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects live listings or scores outside the demo range', () => {
    const live = success(); live.output.recommendations[0].listing.is_demo = false;
    expect(() => parsePropertyDemo(live)).toThrow();
    const invalid = success(); invalid.output.recommendations[0].score = 2;
    expect(() => parsePropertyDemo(invalid)).toThrow();
  });
  it('requires a warning when prices are unknown', () => {
    const body = success(); body.output.recommendations[0].listing.price_aed = null;
    expect(() => parsePropertyDemo(body)).toThrow();
    body.output.recommendations[0].caveats.push('Price not confirmed; verify before quoting.');
    expect(parsePropertyDemo(body).matches[0].price).toBeNull();
  });
  it('accepts an honest empty result', () => {
    const body = success(); body.output.recommendations = []; body.output.contains_demo_data = false; body.output.no_match_reason = 'No eligible demo listings.';
    expect(parsePropertyDemo(body).matches).toHaveLength(0);
  });
});

describe('property matching form', () => {
  it('waits for explicit submission', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); render(<DemoPropertyForm />);
    expect(fetch).not.toHaveBeenCalled(); expect(screen.getByText('Fictional catalog only')).toBeVisible();
  });
  it('shows ranked results, price caveats and source dates', async () => {
    vi.stubGlobal('fetch', fetcher()); render(<DemoPropertyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Match demo properties' }));
    expect(await screen.findByText('Fictional Test Project')).toBeVisible();
    expect(screen.getByText('Illustrative AED 1,450,000')).toBeVisible(); expect(screen.getByText(disclaimer)).toBeVisible();
    expect(screen.getByText(/Data as of 2026-01-01/)).toBeVisible();
  });
  it('shows unknown price without inventing a value', async () => {
    const body = success(); body.output.recommendations[0].listing.price_aed = null; body.output.recommendations[0].caveats.push('Price not confirmed; verify before quoting.');
    vi.stubGlobal('fetch', fetcher(body)); render(<DemoPropertyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Match demo properties' }));
    expect(await screen.findByText('Price needs confirmation')).toBeVisible(); expect(screen.queryByText(/Illustrative AED/)).not.toBeInTheDocument();
  });
  it('displays no matches rather than sample fallback results', async () => {
    const body = success(); body.output.recommendations = []; body.output.contains_demo_data = false; body.output.no_match_reason = 'No eligible demo listings.';
    vi.stubGlobal('fetch', fetcher(body)); render(<DemoPropertyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Match demo properties' }));
    expect(await screen.findByText('No matching demo properties')).toBeVisible();
    expect(screen.queryByText('Fictional Test Project')).not.toBeInTheDocument();
  });
  it('keeps diagnostics out of the visible error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private-value'))); render(<DemoPropertyForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Match demo properties' }));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-value');
  });
  it('locks the form and ignores double submissions', async () => {
    let finish: (value: Response) => void = () => undefined;
    const fetch = vi.fn().mockImplementation(() => new Promise<Response>(resolve => { finish = resolve; })); vi.stubGlobal('fetch', fetch);
    const { container } = render(<DemoPropertyForm />);
    fireEvent.submit(container.querySelector('form')!); fireEvent.submit(container.querySelector('form')!);
    expect(fetch).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('Demo maximum budget (AED)')).toBeDisabled();
    finish(response({}, false)); await screen.findByRole('alert');
  });
  it('aborts the request when unmounted', async () => {
    const fetch = vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    })); vi.stubGlobal('fetch', fetch);
    const { unmount } = render(<DemoPropertyForm />); fireEvent.click(screen.getByRole('button', { name: 'Match demo properties' }));
    const requestSignal = fetch.mock.calls[0][1].signal as AbortSignal; unmount(); expect(requestSignal.aborted).toBe(true);
  });
});
