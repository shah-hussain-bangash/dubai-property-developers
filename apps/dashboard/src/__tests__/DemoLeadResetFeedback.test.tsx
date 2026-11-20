import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoLeadForm } from '@/features/leads/DemoLeadForm';
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

const capability={enabled:true,mock_integrations:true,memory_storage:true};
const duplicate=()=>({...success(),result:{is_duplicate:true,qualification:null,crm:null}});
const run=()=>fireEvent.click(screen.getByRole('button',{name:'Run demo qualification'}));
const complete=()=>screen.findByText('Demo qualification complete');
const twice=()=>fetcher().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(duplicate()));
const fresh=()=>fireEvent.click(screen.getByRole('button',{name:'New fictional lead'}));
const feedback=()=>screen.getByLabelText('New fictional lead feedback');
describe('new fictional lead feedback',()=>{
 it('does not announce a reset or move focus on initial render',()=>{render(<DemoLeadForm/>);expect(feedback()).toBeEmptyDOMElement();expect(screen.getByLabelText('Maximum budget (AED)')).not.toHaveFocus();});
 it('announces readiness and returns focus to the editable budget',()=>{render(<DemoLeadForm/>);fresh();expect(feedback()).toHaveTextContent('New fictional lead ready. Requirements are editable; existing mock records are unchanged.');expect(feedback()).toHaveAttribute('aria-live','polite');expect(feedback()).toHaveAttribute('aria-atomic','true');expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();expect(screen.getByLabelText('Maximum budget (AED)')).toBeEnabled();});
 it('unlocks the completed lead and retains chosen requirements without a request',async()=>{const f=fetcher();vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);fireEvent.change(screen.getByLabelText('Maximum budget (AED)'),{target:{value:'1750000'}});run();await complete();fresh();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(1750000);expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();expect(screen.queryByText('Demo qualification complete')).toBeNull();expect(screen.queryByRole('button',{name:'Download lead report'})).toBeNull();expect(f).toHaveBeenCalledTimes(2);});
 it('clears a failed attempt before moving focus',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('failure')));render(<DemoLeadForm/>);run();await screen.findByRole('alert');fresh();expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();});
 it('clears reset guidance when a new run starts',()=>{vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(()=>{})));render(<DemoLeadForm/>);fresh();run();expect(feedback()).toBeEmptyDOMElement();expect(screen.getByRole('button',{name:'New fictional lead'})).toBeDisabled();});
 it('clears reset guidance when an example replaces the choices',()=>{render(<DemoLeadForm/>);fresh();fireEvent.click(screen.getByRole('button',{name:'Later enquiry example'}));expect(feedback()).toBeEmptyDOMElement();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(750000);});
 it('does not fetch or persist records when starting fresh repeatedly',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);const storage=vi.spyOn(Storage.prototype,'setItem');render(<DemoLeadForm/>);fresh();screen.getByRole('button',{name:'New fictional lead'}).focus();fresh();expect(screen.getByLabelText('Maximum budget (AED)')).toHaveFocus();expect(f).not.toHaveBeenCalled();expect(storage).not.toHaveBeenCalled();});
 it('cannot reset or announce success while a request is pending',()=>{vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(()=>{})));render(<DemoLeadForm/>);run();fresh();expect(feedback()).toBeEmptyDOMElement();expect(screen.getByLabelText('Maximum budget (AED)')).toBeDisabled();expect(screen.getByRole('button',{name:'New fictional lead'})).toBeDisabled();});
});
