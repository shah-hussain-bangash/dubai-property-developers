import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoScenarioForm } from '@/features/workflows/DemoScenarioForm';

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

const duplicate=()=>({...success(),status:'duplicate',lead:{...success().lead,result:{is_duplicate:true,crm:null,qualification:null}},properties:null,reply:null});
const run=()=>fireEvent.click(screen.getByRole('button',{name:'Run guided demo'}));
const retry=()=>fireEvent.click(screen.getByRole('button',{name:'Run same scenario'}));
const complete=()=>screen.findByText('Demo completed — reply awaits review');
function twice(){return fetcher().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(duplicate()));}
const fresh=()=>fireEvent.click(screen.getByRole('button',{name:'New demo scenario'}));
const feedback=()=>screen.getByLabelText('New demo scenario feedback');
describe('new demo scenario feedback',()=>{
 it('does not announce a reset or move focus on initial render',()=>{render(<DemoScenarioForm/>);expect(feedback()).toBeEmptyDOMElement();expect(screen.getByLabelText('Maximum budget (AED)')).not.toHaveFocus();});
 it('announces readiness and returns focus to the editable budget',()=>{render(<DemoScenarioForm/>);fresh();expect(feedback()).toHaveTextContent('New demo scenario ready. Requirements are editable; saved comparisons and mock records are unchanged.');expect(feedback()).toHaveAttribute('aria-live','polite');expect(feedback()).toHaveAttribute('aria-atomic','true');expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();expect(screen.getByLabelText('Maximum budget (AED)')).toBeEnabled();});
 it('unlocks the completed lead and retains chosen requirements without a request',async()=>{const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoScenarioForm/>);fireEvent.change(screen.getByLabelText('Maximum budget (AED)'),{target:{value:'1750000'}});run();await complete();fresh();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(1750000);expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();expect(screen.queryByText('Demo completed — reply awaits review')).toBeNull();expect(screen.getByRole('table')).toBeVisible();expect(screen.queryByRole('button',{name:'Download demo report'})).toBeNull();expect(f).toHaveBeenCalledTimes(2);});
 it('clears a failed attempt before moving focus',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('failure')));render(<DemoScenarioForm/>);run();await screen.findByRole('alert');fresh();expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();});
 it('clears reset guidance when a new run starts',()=>{vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(()=>{})));render(<DemoScenarioForm/>);fresh();run();expect(feedback()).toBeEmptyDOMElement();expect(screen.getByRole('button',{name:'New demo scenario'})).toBeDisabled();});
 it('clears reset guidance when an example replaces the choices',()=>{render(<DemoScenarioForm/>);fresh();fireEvent.click(screen.getByRole('button',{name:'No-match budget example'}));expect(feedback()).toBeEmptyDOMElement();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(1000);});
 it('does not fetch or persist records when starting fresh repeatedly',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);const storage=vi.spyOn(Storage.prototype,'setItem');render(<DemoScenarioForm/>);fresh();screen.getByRole('button',{name:'New demo scenario'}).focus();fresh();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();expect(f).not.toHaveBeenCalled();expect(storage).not.toHaveBeenCalled();});
 it('cannot reset or announce success while a request is pending',()=>{vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(()=>{})));render(<DemoScenarioForm/>);run();fresh();expect(feedback()).toBeEmptyDOMElement();expect(screen.getByLabelText('Maximum budget (AED)')).toBeDisabled();expect(screen.getByRole('button',{name:'New demo scenario'})).toBeDisabled();});
});
