import { afterEach,expect,it,vi } from 'vitest';
import { cleanup,render,screen } from '@testing-library/react';
import { downloadProspectReport } from '@/services/prospectReports';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
import { accessProspectDatabase } from '@/services/prospectDatabase';
import { emptyWorkspace } from '@/services/prospectResearch';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();vi.useRealTimers();});
it('downloads one combined PDF from the saved revision without write requests',async()=>{
  vi.useFakeTimers();const blob={size:30,slice:()=>({arrayBuffer:async()=>new TextEncoder().encode('%PDF-').buffer})};
  const fetch=vi.fn().mockResolvedValue({status:200,ok:true,headers:new Headers({'content-type':'application/pdf'}),blob:async()=>blob});vi.stubGlobal('fetch',fetch);
  const NativeURL=URL;vi.stubGlobal('URL',class extends NativeURL{static createObjectURL=vi.fn().mockReturnValue('blob:batch');static revokeObjectURL=vi.fn();});
  let name='';vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){name=this.download;});
  await downloadProspectReport(9,undefined,true);expect(fetch.mock.calls[0][0]).toContain('/reports.pdf?revision=9');expect(fetch.mock.calls[0][1].method).toBeUndefined();expect(name).toMatch(/^prospect-batch-\d{4}-\d{2}-\d{2}\.pdf$/);vi.runAllTimers();
});
it('keeps the combined report disabled for an empty workspace',async()=>{
  vi.mocked(accessProspectDatabase).mockResolvedValue({revision:1,workspace:emptyWorkspace()});render(<ProspectResearchWorkspace/>);await screen.findByText(/Storage: PostgreSQL/);expect(screen.getByRole('button',{name:'Download all prospects in one PDF'})).toBeDisabled();
});
