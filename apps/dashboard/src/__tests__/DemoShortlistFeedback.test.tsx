import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoPropertyForm } from '@/features/properties/DemoPropertyForm';
import { DemoPropertyShortlist } from '@/features/properties/DemoPropertyShortlist';
import { toggleDemoShortlist } from '@/services/demoPropertyShortlist';
import { parsePropertyDemo } from '@/services/demoProperties';

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

const match=()=>parsePropertyDemo(success()).matches[0];
describe('shortlist selection feedback',()=>{
 const one=()=>({...match(),name:'Fictional One'});
 const two=()=>({...match(),id:'DEMO-002',name:'Fictional Two'});
 const three=()=>({...match(),id:'DEMO-003',name:'Fictional Three'});
 it('does not announce a selection on initial render',()=>{render(<DemoPropertyShortlist items={[one()]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByLabelText('Shortlist selection feedback')).toBeEmptyDOMElement();});
 it('announces added property and count in an atomic polite region',()=>{const {rerender}=render(<DemoPropertyShortlist items={[]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);rerender(<DemoPropertyShortlist items={[one()]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByLabelText('Shortlist selection feedback')).toHaveTextContent('Added Fictional One. Shortlist: 1 of 3.');expect(screen.getByLabelText('Shortlist selection feedback')).toHaveAttribute('aria-atomic','true');expect(screen.getByLabelText('Shortlist selection feedback')).toHaveAttribute('aria-live','polite');});
 it('announces removal without claiming the entire shortlist was cleared',()=>{const a=one(),b=two();const {rerender}=render(<DemoPropertyShortlist items={[a,b]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);rerender(<DemoPropertyShortlist items={[b]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByLabelText('Shortlist selection feedback')).toHaveTextContent('Removed Fictional One. Shortlist: 1 of 3.');});
 it('announces clearing multiple saved properties',()=>{const {rerender}=render(<DemoPropertyShortlist items={[one(),two()]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);rerender(<DemoPropertyShortlist items={[]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByLabelText('Shortlist selection feedback')).toHaveTextContent('Shortlist cleared. Shortlist: 0 of 3.');});
 it('explains capacity and removes the guidance when space becomes available',()=>{const a=one(),b=two(),c=three();const {rerender}=render(<DemoPropertyShortlist items={[a,b,c]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByText('Shortlist full: remove a saved property before adding another.')).toBeVisible();rerender(<DemoPropertyShortlist items={[a,b]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.queryByText(/Shortlist full:/)).toBeNull();});
 it('does not announce a false addition when snapshots keep the same identities',()=>{const a=one();const {rerender}=render(<DemoPropertyShortlist items={[a]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);rerender(<DemoPropertyShortlist items={[{...a}]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByLabelText('Shortlist selection feedback')).toBeEmptyDOMElement();});
 it('announces real local form actions without additional requests',async()=>{const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoPropertyForm/>);fireEvent.click(screen.getByRole('button',{name:'Match demo properties'}));fireEvent.click(await screen.findByRole('button',{name:'Add DEMO-001 to shortlist'}));expect(screen.getByText('Added Fictional Test Project. Shortlist: 1 of 3.')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Remove saved DEMO-001 from shortlist'}));expect(screen.getByText('Removed Fictional Test Project. Shortlist: 0 of 3.')).toBeVisible();expect(f).toHaveBeenCalledTimes(2);});
 it('escapes property names in announcements',()=>{const item={...one(),name:'<script>fictional</script>'};const {rerender,container}=render(<DemoPropertyShortlist items={[]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);rerender(<DemoPropertyShortlist items={[item]} busy={false} onClear={()=>{}} onRemove={()=>{}}/>);expect(screen.getByLabelText('Shortlist selection feedback')).toHaveTextContent('Added <script>fictional</script>.');expect(container.querySelector('script')).toBeNull();});
});
