import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoScenarioForm } from '@/features/workflows/DemoScenarioForm';
import { rememberScenario } from '@/services/demoScenarioHistory';
import { DemoScenarioComparison } from '@/features/workflows/DemoScenarioComparison';
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

const snapshot=(key:string)=>rememberScenario([],choices,parseScenario(success()),key)[0];
const props={busy:false,onClear:()=>{}};
const feedback=()=>screen.getByLabelText('Scenario comparison feedback');
describe('scenario comparison feedback',()=>{
 it('starts without a misleading change announcement',()=>{render(<DemoScenarioComparison {...props} items={[snapshot('one')]}/>);expect(feedback()).toBeEmptyDOMElement();});
 it('announces new scenarios with a polite atomic count',()=>{const {rerender}=render(<DemoScenarioComparison {...props} items={[]}/>);rerender(<DemoScenarioComparison {...props} items={[snapshot('one')]}/>);expect(feedback()).toHaveTextContent('Scenario added to comparison. 1 of 3 saved.');expect(feedback()).toHaveAttribute('aria-live','polite');expect(feedback()).toHaveAttribute('aria-atomic','true');});
 it('does not announce cloned snapshots as new scenarios',()=>{const item=snapshot('one');const {rerender}=render(<DemoScenarioComparison {...props} items={[item]}/>);rerender(<DemoScenarioComparison {...props} items={[{...item}]}/>);expect(feedback()).toBeEmptyDOMElement();});
 it('explains oldest-item eviction at the three-scenario limit',()=>{const a=snapshot('a'),b=snapshot('b'),c=snapshot('c'),d=snapshot('d');const {rerender}=render(<DemoScenarioComparison {...props} items={[c,b,a]}/>);rerender(<DemoScenarioComparison {...props} items={[d,c,b]}/>);expect(feedback()).toHaveTextContent('3 of 3 saved. Oldest comparison removed; latest three retained.');expect(screen.getAllByRole('row')).toHaveLength(4);});
 it('explains that clearing preserves the current result and mock records',()=>{const {rerender}=render(<DemoScenarioComparison {...props} items={[snapshot('a')]}/>);rerender(<DemoScenarioComparison {...props} items={[]}/>);expect(feedback()).toHaveTextContent('Comparison cleared. Current scenario result and mock CRM records are unchanged.');expect(screen.queryByRole('table')).toBeNull();});
 it('keeps clear local without any fetch or persistent storage',()=>{const f=vi.fn(),clear=vi.fn();vi.stubGlobal('fetch',f);const storage=vi.spyOn(Storage.prototype,'setItem');render(<DemoScenarioComparison {...props} onClear={clear} items={[snapshot('a')]}/>);fireEvent.click(screen.getByRole('button',{name:'Clear comparison'}));expect(clear).toHaveBeenCalledOnce();expect(f).not.toHaveBeenCalled();expect(storage).not.toHaveBeenCalled();});
 it('keeps clear disabled during a run',()=>{const clear=vi.fn();render(<DemoScenarioComparison {...props} busy={true} onClear={clear} items={[snapshot('a')]}/>);fireEvent.click(screen.getByRole('button',{name:'Clear comparison'}));expect(clear).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Clear comparison'})).toBeDisabled();});
 it('announces no-match snapshots without inventing a reply',()=>{const item={...snapshot('a'),outcome:'no_matches' as const,matches:[]};const {rerender}=render(<DemoScenarioComparison {...props} items={[]}/>);rerender(<DemoScenarioComparison {...props} items={[item]}/>);expect(feedback()).toHaveTextContent('1 of 3 saved.');expect(screen.getByText('Skipped — no matches')).toBeVisible();expect(screen.queryByText('Unsent draft; human review required')).toBeNull();});
});
