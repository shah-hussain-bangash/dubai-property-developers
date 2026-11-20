import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoPropertyForm } from '@/features/properties/DemoPropertyForm';

const disclaimer = 'Prices must be confirmed with the developer. No investment return is implied or guaranteed.';
const success = () => ({ dev_only: true, uses_mock_integrations: true, status: 'succeeded', output: {
  contains_demo_data: true, no_match_reason: null as string | null, disclaimer,
  recommendations: [{ score: 0.8, reasons: ['Matches demo criteria'], caveats: ['DEMO DATA: fictional listing.', 'No return is guaranteed.'],
    listing: { is_demo: true, source: 'demo-seed', listing_id: 'DEMO-001', project_name: 'Fictional Test Project',
      community: 'Dubai Marina', bedrooms: 1, price_aed: '1450000' as string | null, data_as_of: '2026-01-01', availability: 'available' } }] } });
const response = (body: unknown, ok = true) => ({ ok, json: async () => body } as Response);
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const fetcher = (body: unknown = success()) => vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(body));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

const run=()=>fireEvent.click(screen.getByRole('button',{name:'Match demo properties'}));
const ready=()=>screen.findByRole('button',{name:'Add DEMO-001 to shortlist'});
describe('property results follow current requirements',()=>{
  it.each([
    ['Demo maximum budget (AED)','3000000'],
    ['Preferred location','Dubai Marina'],
    ['Preferred bedrooms','2'],
  ])('clears matches when %s changes without making a request',async(label,value)=>{
    const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();await ready();
    fireEvent.change(screen.getByLabelText(label),{target:{value}});
    expect(screen.queryByRole('button',{name:'Add DEMO-001 to shortlist'})).toBeNull();
    expect(screen.getByText(/Requirements changed/)).toBeVisible();expect(f).toHaveBeenCalledTimes(2);
  });
  it('clears matches when the payment plan changes',async()=>{
    const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();await ready();fireEvent.click(screen.getByLabelText('Payment plan required'));
    expect(screen.queryByText('1 demo match')).toBeNull();expect(f).toHaveBeenCalledTimes(2);
  });
  it('retains saved listing snapshots after requirements change',async()=>{
    const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();fireEvent.click(await ready());
    fireEvent.change(screen.getByLabelText('Preferred location'),{target:{value:'Business Bay'}});
    expect(screen.getByText('Shortlisted: Fictional Test Project')).toBeVisible();expect(screen.getByText('Fictional property shortlist (1/3)')).toBeVisible();expect(f).toHaveBeenCalledTimes(2);
  });
  it('submits edited requirements only after an explicit new match',async()=>{
    const f=fetcher().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(success()));vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();await ready();
    fireEvent.change(screen.getByLabelText('Demo maximum budget (AED)'),{target:{value:'3000000'}});run();await ready();
    expect(screen.queryByText(/Requirements changed/)).toBeNull();expect(f).toHaveBeenCalledTimes(4);expect(JSON.parse(f.mock.calls[3][1].body).budget_max_aed).toBe('3000000');
  });
  it('clears a prior no-match result on edit',async()=>{
    const empty=success();empty.output.recommendations=[];empty.output.contains_demo_data=false;empty.output.no_match_reason='No eligible fictional listings';
    vi.stubGlobal('fetch',fetcher(empty));render(<DemoPropertyForm/>);run();await screen.findByText('No matching demo properties');fireEvent.click(screen.getByLabelText('Payment plan required'));expect(screen.queryByText('No matching demo properties')).toBeNull();expect(screen.getByText(/Requirements changed/)).toBeVisible();
  });
  it('clears an old error on edit without matching automatically',async()=>{
    const f=vi.fn().mockRejectedValue(new Error('failure'));vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();await screen.findByRole('alert');fireEvent.change(screen.getByLabelText('Preferred bedrooms'),{target:{value:'2'}});expect(screen.queryByRole('alert')).toBeNull();expect(f).toHaveBeenCalledTimes(1);
  });
});
