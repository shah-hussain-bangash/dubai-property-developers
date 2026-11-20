import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { downloadProspectReport } from '@/services/prospectReports';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
import { accessProspectDatabase } from '@/services/prospectDatabase';
import { emptyWorkspace } from '@/services/prospectResearch';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();vi.useRealTimers();});
it('does not fetch invalid record IDs or revisions',async()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
  await expect(downloadProspectReport(2,'../private')).rejects.toThrow();
  await expect(downloadProspectReport(-1)).rejects.toThrow();expect(fetch).not.toHaveBeenCalled();
});
it('rejects stale exports and does not retry',async()=>{
  const fetch=vi.fn().mockResolvedValue({status:409,ok:false});vi.stubGlobal('fetch',fetch);
  await expect(downloadProspectReport(2,'example-id')).rejects.toThrow('Reload');expect(fetch).toHaveBeenCalledTimes(1);
});
it('explains unsupported scripts and rejects unverified content types',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce({status:422,ok:false}).mockResolvedValueOnce({status:200,ok:true,headers:new Headers({'content-type':'text/html'})});vi.stubGlobal('fetch',fetch);
  await expect(downloadProspectReport(2)).rejects.toThrow('font');await expect(downloadProspectReport(2)).rejects.toThrow('could not be downloaded');
});
it('downloads a verified PDF with a safe filename and no credentials',async()=>{
  vi.useFakeTimers();
  const blob={size:30,slice:()=>({arrayBuffer:async()=>new TextEncoder().encode('%PDF-').buffer})};
  const fetch=vi.fn().mockResolvedValue({status:200,ok:true,headers:new Headers({'content-type':'application/pdf'}),blob:async()=>blob});vi.stubGlobal('fetch',fetch);
  const create=vi.fn().mockReturnValue('blob:test');const NativeURL=URL;vi.stubGlobal('URL',class extends NativeURL {static createObjectURL=create;static revokeObjectURL=vi.fn();});
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  await downloadProspectReport(4,'example-id');expect(click).toHaveBeenCalledOnce();expect(fetch.mock.calls[0][0]).toContain('example-id.pdf?revision=4');expect(fetch.mock.calls[0][1].credentials).toBe('omit');expect(create).toHaveBeenCalledOnce();vi.runAllTimers();vi.useRealTimers();
});
it('does not start an export on page load and disables a batch without records',async()=>{
  localStorage.clear();vi.mocked(accessProspectDatabase).mockResolvedValue({revision:0,workspace:emptyWorkspace()});const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
  render(<ProspectResearchWorkspace/>);await screen.findByText(/Storage: PostgreSQL/);
  expect(screen.getByRole('button',{name:'Download all prospect PDFs (ZIP)'})).toBeDisabled();expect(fetch).not.toHaveBeenCalled();
});
it('uses the saved revision when a person requests a prospect PDF',async()=>{
  localStorage.clear();vi.mocked(accessProspectDatabase).mockResolvedValue({revision:7,workspace:{...emptyWorkspace(),prospects:[{id:'example-id',name:'Example Person',company:'Example Co',role:'Director',country:'UAE',email:'',phone:'',source:'https://example.com',relevance:'Fictional test profile',collectedAt:'2026-10-26T12:00:00Z',status:'pending'}]}});
  const fetch=vi.fn().mockResolvedValue({status:409,ok:false});vi.stubGlobal('fetch',fetch);render(<ProspectResearchWorkspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Download prospect PDF'}));expect(await screen.findByRole('alert')).toHaveTextContent('Reload');expect(fetch.mock.calls[0][0]).toContain('example-id.pdf?revision=7');expect(accessProspectDatabase).toHaveBeenCalledTimes(1);
});
