import { afterEach, expect, it, vi } from 'vitest';
import { accessProspectDatabase, parseDatabaseWorkspace } from '@/services/prospectDatabase';
import { emptyWorkspace } from '@/services/prospectResearch';
afterEach(()=>vi.unstubAllGlobals());
it('rejects unverified storage provenance and invalid revisions',()=>{
  const valid={storage:'postgresql',outreach_enabled:false,revision:1,workspace:emptyWorkspace()};
  expect(parseDatabaseWorkspace(valid).revision).toBe(1);
  for(const update of [{storage:'memory'},{outreach_enabled:true},{revision:-1},{revision:1.5}])expect(()=>parseDatabaseWorkspace({...valid,...update})).toThrow();
});
it('never retries a write after a revision conflict',async()=>{
  const fetch=vi.fn().mockResolvedValue({status:409,ok:false});vi.stubGlobal('fetch',fetch);
  await expect(accessProspectDatabase({revision:2,workspace:emptyWorkspace()})).rejects.toThrow('Another session');
  expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][1].credentials).toBe('omit');expect(fetch.mock.calls[0][1].redirect).toBe('error');
});
it('sends the expected revision and verifies the returned database snapshot',async()=>{
  const fetch=vi.fn().mockResolvedValue({status:200,ok:true,json:async()=>({storage:'postgresql',outreach_enabled:false,revision:3,workspace:emptyWorkspace()})});vi.stubGlobal('fetch',fetch);
  expect((await accessProspectDatabase({revision:2,workspace:emptyWorkspace()})).revision).toBe(3);
  expect(JSON.parse(fetch.mock.calls[0][1].body).revision).toBe(2);
});
