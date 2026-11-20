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

import { demoPropertyExamples, demoPropertyExampleChoices, type DemoPropertyExampleId } from '@/services/demoPropertyPresets';
const run=()=>fireEvent.click(screen.getByRole('button',{name:'Match demo properties'}));
const ready=()=>screen.findByRole('button',{name:'Add DEMO-001 to shortlist'});
describe('fictional property examples',()=>{
 it('returns distinct fresh choice objects without sharing edits',()=>{expect(demoPropertyExamples).toHaveLength(3);for(const e of demoPropertyExamples){const a=demoPropertyExampleChoices(e.id);const b=demoPropertyExampleChoices(e.id);expect(a).toEqual(b);expect(a).not.toBe(b);}const a=demoPropertyExampleChoices('marina');a.budget='1';expect(demoPropertyExampleChoices('marina').budget).toBe('2500000');});
 it('rejects an unknown example without silently choosing a fallback',()=>{expect(()=>demoPropertyExampleChoices('unknown' as DemoPropertyExampleId)).toThrow();});
 it('fills Marina criteria without searching automatically',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);fireEvent.click(screen.getByRole('button',{name:'Marina apartment example'}));expect(screen.getByLabelText('Demo maximum budget (AED)')).toHaveValue(2500000);expect(screen.getByLabelText('Preferred location')).toHaveValue('Dubai Marina');expect(screen.getByLabelText('Preferred bedrooms')).toHaveValue('2');expect(screen.getByLabelText('Payment plan required')).not.toBeChecked();expect(f).not.toHaveBeenCalled();});
 it('fills the studio and payment-plan criteria while allowing edits',()=>{vi.stubGlobal('fetch',vi.fn());render(<DemoPropertyForm/>);fireEvent.click(screen.getByRole('button',{name:'JVC studio example'}));expect(screen.getByLabelText('Preferred bedrooms')).toHaveValue('0');expect(screen.getByLabelText('Payment plan required')).toBeChecked();expect(screen.getByLabelText('Preferred location')).toHaveValue('Jumeirah Village Circle');fireEvent.change(screen.getByLabelText('Demo maximum budget (AED)'),{target:{value:'900000'}});expect(screen.getByLabelText('Demo maximum budget (AED)')).toHaveValue(900000);});
 it('fills a deliberately small budget without fabricating a no-match result before submission',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);fireEvent.click(screen.getByRole('button',{name:'No-match search example'}));expect(screen.getByLabelText('Demo maximum budget (AED)')).toHaveValue(1000);expect(screen.getByLabelText('Preferred location')).toHaveValue('Business Bay');expect(screen.getByLabelText('Preferred bedrooms')).toHaveValue('1');expect(screen.queryByText('No matching demo properties')).toBeNull();expect(f).not.toHaveBeenCalled();});
 it('clears stale matches but keeps saved snapshots when selecting an example',async()=>{const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();fireEvent.click(await ready());fireEvent.click(screen.getByRole('button',{name:'No-match search example'}));expect(screen.queryByRole('button',{name:'Add DEMO-001 to shortlist'})).toBeNull();expect(screen.getByText('Shortlisted: Fictional Test Project')).toBeVisible();expect(screen.getByText(/Requirements changed/)).toBeVisible();expect(f).toHaveBeenCalledTimes(2);});
 it('submits the selected example only on explicit search and disables examples while pending',async()=>{const f=fetcher().mockReturnValueOnce(new Promise(()=>{}));vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);fireEvent.click(screen.getByRole('button',{name:'Marina apartment example'}));run();await ready();expect(JSON.parse(f.mock.calls[1][1].body)).toMatchObject({budget_max_aed:'2500000'});run();for(const e of demoPropertyExamples)expect(screen.getByRole('button',{name:e.label})).toBeDisabled();});
 it('clears an old failure without an automatic retry',async()=>{const f=vi.fn().mockRejectedValue(new Error('failure'));vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'JVC studio example'}));expect(screen.queryByRole('alert')).toBeNull();expect(f).toHaveBeenCalledTimes(1);});
});
