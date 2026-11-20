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

import { demoLeadExamples, demoLeadExampleChoices, type DemoLeadExampleId } from '@/services/demoLeadPresets';
const run=()=>fireEvent.click(screen.getByRole('button',{name:'Run demo qualification'}));
describe('fictional lead examples',()=>{
 it('returns fresh complete choice objects for the three distinct examples',()=>{expect(demoLeadExamples).toHaveLength(3);for(const e of demoLeadExamples){const a=demoLeadExampleChoices(e.id);const b=demoLeadExampleChoices(e.id);expect(a).toEqual(b);expect(a).not.toBe(b);expect(Number(a.budget)).toBeGreaterThan(0);expect(['investment','end_use']).toContain(a.purpose);}const a=demoLeadExampleChoices('later');a.budget='1';expect(demoLeadExampleChoices('later').budget).toBe('750000');});
 it('rejects an unknown example without a fallback',()=>{expect(()=>demoLeadExampleChoices('unknown' as DemoLeadExampleId)).toThrow();});
 it('fills near-term apartment requirements without a request',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);fireEvent.click(screen.getByRole('button',{name:'Near-term apartment example'}));expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(1500000);expect(screen.getByLabelText('Buying timeline')).toHaveValue('1');expect(screen.getByLabelText('Bedrooms')).toHaveValue('1');expect(f).not.toHaveBeenCalled();});
 it('fills later studio investment requirements without a request',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);fireEvent.click(screen.getByRole('button',{name:'Later enquiry example'}));expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(750000);expect(screen.getByLabelText('Buying timeline')).toHaveValue('12');expect(screen.getByLabelText('Location')).toHaveValue('Jumeirah Village Circle');expect(screen.getByLabelText('Bedrooms')).toHaveValue('0');expect(f).not.toHaveBeenCalled();});
 it('fills own-home requirements and allows editing before submission',()=>{vi.stubGlobal('fetch',vi.fn());render(<DemoLeadForm/>);fireEvent.click(screen.getByRole('button',{name:'Own-home studio example'}));expect(screen.getByLabelText('Purpose')).toHaveValue('end_use');fireEvent.change(screen.getByLabelText('Maximum budget (AED)'),{target:{value:'1200000'}});expect(screen.getByLabelText('Maximum budget (AED)')).toHaveValue(1200000);});
 it('clears a previous result and uses a new contact on the next explicit run',async()=>{const cap={enabled:true,mock_integrations:true,memory_storage:true};const f=fetcher().mockResolvedValueOnce(response(cap)).mockResolvedValueOnce(response(success()));vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await screen.findByText('Demo qualification complete');fireEvent.click(screen.getByRole('button',{name:'Later enquiry example'}));expect(screen.queryByText('Demo qualification complete')).toBeNull();expect(screen.getByLabelText('Maximum budget (AED)')).not.toBeDisabled();expect(f).toHaveBeenCalledTimes(2);run();await screen.findByText('Demo qualification complete');const a=JSON.parse(f.mock.calls[1][1].body);const b=JSON.parse(f.mock.calls[3][1].body);expect(a.email).not.toBe(b.email);expect(b.budget_max_aed).toBe('750000');});
 it('disables examples during a request',()=>{vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(()=>{})));render(<DemoLeadForm/>);run();for(const e of demoLeadExamples)expect(screen.getByRole('button',{name:e.label})).toBeDisabled();});
 it('clears an old error on selecting an example without retrying automatically',async()=>{const f=vi.fn().mockRejectedValue(new Error('failure'));vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Near-term apartment example'}));expect(screen.queryByRole('alert')).toBeNull();expect(f).toHaveBeenCalledTimes(1);});
});
