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
describe('lead retry preserves qualification',()=>{
 it('keeps score, reasons and routing when a repeat is rejected',async()=>{const f=twice();vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await complete();run();await screen.findByText(/Duplicate retry stopped/);expect(screen.getByText('Demo qualification complete')).toBeVisible();expect(screen.getByText('sales-standard')).toBeVisible();expect(screen.getByText(/Budget supplied/)).toBeVisible();expect(screen.queryByText('Duplicate demo detected')).toBeNull();expect(f).toHaveBeenCalledTimes(4);expect(JSON.parse(f.mock.calls[1][1].body)).toEqual(JSON.parse(f.mock.calls[3][1].body));});
 it('still reports a duplicate when no earlier result exists',async()=>{vi.stubGlobal('fetch',fetcher(duplicate()));render(<DemoLeadForm/>);run();await screen.findByText('Duplicate demo detected');expect(screen.queryByText(/Duplicate retry stopped/)).toBeNull();});
 it('retains prior qualification after a failed retry without automatic retries',async()=>{const f=fetcher().mockRejectedValueOnce(new Error('failure'));vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await complete();run();await screen.findByRole('alert');expect(screen.getByText('Demo qualification complete')).toBeVisible();expect(screen.getByText('sales-standard')).toBeVisible();expect(f).toHaveBeenCalledTimes(3);});
 it('keeps prior details visible while disabling actions during a retry',async()=>{vi.stubGlobal('fetch',fetcher().mockReturnValueOnce(new Promise(()=>{})));render(<DemoLeadForm/>);run();await complete();run();expect(screen.getByText('Demo qualification complete')).toBeVisible();expect(screen.getByRole('button',{name:'New fictional lead'})).toBeDisabled();expect(screen.getByLabelText('Maximum budget (AED)')).toBeDisabled();});
 it('explicitly starting a new lead clears prior details and repeat guidance',async()=>{vi.stubGlobal('fetch',twice());render(<DemoLeadForm/>);run();await complete();run();await screen.findByText(/Duplicate retry stopped/);fireEvent.click(screen.getByRole('button',{name:'New fictional lead'}));expect(screen.queryByText('Demo qualification complete')).toBeNull();expect(screen.queryByText(/Duplicate retry stopped/)).toBeNull();expect(screen.getByLabelText('Maximum budget (AED)')).not.toBeDisabled();});
 it('a new contact can replace the earlier score with a fresh qualification',async()=>{const second=success();second.result.qualification.score.score=91;const f=fetcher().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(second));vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await complete();fireEvent.click(screen.getByRole('button',{name:'New fictional lead'}));run();await complete();expect(screen.getByText('91 / 100')).toBeVisible();expect(JSON.parse(f.mock.calls[1][1].body).email).not.toBe(JSON.parse(f.mock.calls[3][1].body).email);});
 it('a duplicate after a failed first attempt does not invent a qualification',async()=>{const f=vi.fn().mockRejectedValueOnce(new Error('failure')).mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(duplicate()));vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await screen.findByRole('alert');run();await screen.findByText('Duplicate demo detected');expect(screen.queryByText('Why this score')).toBeNull();expect(screen.queryByText(/Duplicate retry stopped/)).toBeNull();});
 it('starting over after an error clears the error and retained details without a request',async()=>{const f=fetcher().mockRejectedValueOnce(new Error('failure'));vi.stubGlobal('fetch',f);render(<DemoLeadForm/>);run();await complete();run();await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'New fictional lead'}));expect(screen.queryByRole('alert')).toBeNull();expect(screen.queryByText('Demo qualification complete')).toBeNull();expect(f).toHaveBeenCalledTimes(3);});
});
