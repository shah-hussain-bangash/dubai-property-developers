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

import { DemoPropertyShortlist } from '@/features/properties/DemoPropertyShortlist';
import { parsePropertyDemo } from '@/services/demoProperties';
import { formatPropertySearchReport } from '@/services/demoPropertySearchReport';
import { formatPropertyShortlist } from '@/services/demoPropertyShortlistReport';
const choices={budget:'2000000',location:'any',bedrooms:'any',paymentPlan:false};
const unknown=()=>{const body=success();body.output.recommendations[0].listing.availability='unknown';return body;};
const run=()=>fireEvent.click(screen.getByRole('button',{name:'Match demo properties'}));
const notice='Availability not verified: confirm before offering.';
describe('unknown property availability disclosure',()=>{
 it('shows an explicit availability warning for an unknown-availability search result',async()=>{vi.stubGlobal('fetch',fetcher(unknown()));render(<DemoPropertyForm/>);run();await screen.findByRole('button',{name:'Add DEMO-001 to shortlist'});expect(screen.getByText(notice)).toBeVisible();expect(screen.getByText(/Catalog status: unknown/)).toBeVisible();expect(screen.queryByText('Budget fit not verified: price is unconfirmed.')).toBeNull();});
 it('does not claim an ordinary priced result is unconfirmed',async()=>{vi.stubGlobal('fetch',fetcher());render(<DemoPropertyForm/>);run();await screen.findByRole('button',{name:'Add DEMO-001 to shortlist'});expect(screen.queryByText(notice)).toBeNull();expect(screen.queryByText(/Some returned listings have unconfirmed prices/)).toBeNull();});
 it('retains the warning in a saved shortlist without changing the price',()=>{const item=parsePropertyDemo(unknown()).matches[0];render(<DemoPropertyShortlist items={[item]} busy={false} onRemove={()=>{}} onClear={()=>{}}/>);expect(screen.getByText(notice)).toBeVisible();expect(screen.getByText('Illustrative AED 1,450,000')).toBeVisible();expect(item.availability).toBe('unknown');});
 it('keeps known shortlist prices labelled as illustrative',()=>{render(<DemoPropertyShortlist items={parsePropertyDemo(success()).matches} busy={false} onRemove={()=>{}} onClear={()=>{}}/>);expect(screen.queryByText(notice)).toBeNull();expect(screen.getByText('Illustrative AED 1,450,000')).toBeVisible();});
 it('includes the warning in search reports while preserving filters and dates',()=>{const result=parsePropertyDemo(unknown());const before=JSON.stringify(result);const text=formatPropertySearchReport(choices,result);expect(text).toContain(notice);expect(text).toContain('Catalog status: unknown');expect(text).toContain('AED 2000000');expect(text).toContain('2026-01-01');expect(JSON.stringify(result)).toBe(before);});
 it('includes the warning in shortlist reports without inventing a price',()=>{const item=parsePropertyDemo(unknown()).matches[0];const text=formatPropertyShortlist([item]);expect(text).toContain(notice);expect(text).toContain('Catalog status: unknown');expect(text).toContain('Illustrative price: AED 1450000');expect(item.availability).toBe('unknown');});
 it('does not add the unknown-availability warning to fully priced reports',()=>{const result=parsePropertyDemo(success());expect(formatPropertySearchReport(choices,result)).not.toContain(notice);expect(formatPropertyShortlist(result.matches)).not.toContain(notice);});
 it('preserves saved unknown-availability warnings after an example clears search results',async()=>{const f=fetcher(unknown());vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);run();fireEvent.click(await screen.findByRole('button',{name:'Add DEMO-001 to shortlist'}));fireEvent.click(screen.getByRole('button',{name:'Marina apartment example'}));expect(screen.getByText(notice)).toBeVisible();expect(screen.queryByText(/Some returned listings have unconfirmed prices/)).toBeNull();expect(screen.getByText('Shortlisted: Fictional Test Project')).toBeVisible();expect(f).toHaveBeenCalledTimes(2);});
});
