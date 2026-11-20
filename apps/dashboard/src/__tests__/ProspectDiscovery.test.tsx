import { cleanup,fireEvent,render,screen } from '@testing-library/react';
import { afterEach,expect,it,vi } from 'vitest';
import { ProspectDiscovery } from '@/features/prospects/ProspectDiscovery';
import { parseDiscovery } from '@/services/prospectDiscovery';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
import { accessProspectDatabase } from '@/services/prospectDatabase';
import { emptyWorkspace } from '@/services/prospectResearch';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const cap={enabled:true,provider:'serpapi',daily_limit:1,automatic_collection:false,outreach_enabled:false};
const candidate={id:'a'.repeat(24),title:'Fictional business profile',url:'https://example.com/team',snippet:'A fictional company director profile. Interest unknown.'};
const result={provider:'serpapi',engine:'google',query:'Dubai property investor business contact',scope:'web',searched_at:'2026-10-26T12:00:00Z',results:[candidate],contacts_saved:false,outreach_enabled:false,automatic_collection:false};
const response=(body:unknown,status=200)=>({ok:status===200,status,json:async()=>body});
it('makes no request until the person checks the connection',()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);
  expect(fetch).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Search public profiles once'})).toBeDisabled();
});
it('keeps search disabled without a configured provider',async()=>{
  const fetch=vi.fn().mockResolvedValue(response({...cap,enabled:false,provider:'disabled'}));vi.stubGlobal('fetch',fetch);render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));expect(await screen.findByText(/Search provider not connected/)).toBeVisible();expect(fetch).toHaveBeenCalledTimes(1);expect(screen.getByRole('button',{name:'Search public profiles once'})).toBeDisabled();
});
it('searches once and only stages a source when explicitly selected',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response(cap)).mockResolvedValueOnce(response(result));vi.stubGlobal('fetch',fetch);const choose=vi.fn();render(<ProspectDiscovery disabled={false} onChoose={choose}/>);
  fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));await screen.findByText(/connection configured/);
  fireEvent.click(screen.getByRole('button',{name:'Search public profiles once'}));await screen.findByRole('heading',{name:candidate.title});expect(fetch).toHaveBeenCalledTimes(2);expect(choose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Use source in prospect form'}));expect(choose).toHaveBeenCalledWith(candidate);
  expect(fetch.mock.calls[1][1].credentials).toBe('omit');
});
it('does not retry a daily-limit response',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response(cap)).mockResolvedValueOnce(response({},429));vi.stubGlobal('fetch',fetch);render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));await screen.findByText(/connection configured/);fireEvent.click(screen.getByRole('button',{name:'Search public profiles once'}));expect(await screen.findByRole('alert')).toHaveTextContent('Daily search-attempt limit');expect(fetch).toHaveBeenCalledTimes(2);
});
it('rejects wrong provider provenance and unsafe result links',()=>{
  expect(parseDiscovery(result,result.query,'web').results).toHaveLength(1);
  for(const update of [{contacts_saved:true},{automatic_collection:true},{results:[{...candidate,url:'javascript:alert(1)'}]},{provider:'mock'}])expect(()=>parseDiscovery({...result,...update},result.query,'web')).toThrow();
});
it('does not present non-LinkedIn results as LinkedIn candidates',()=>{
  expect(()=>parseDiscovery({...result,scope:'linkedin'},result.query,'linkedin')).toThrow('scope');
});
it('clears old results when the query changes',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response(cap)).mockResolvedValueOnce(response(result));vi.stubGlobal('fetch',fetch);render(<ProspectDiscovery disabled={false} onChoose={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));await screen.findByText(/connection configured/);fireEvent.click(screen.getByRole('button',{name:'Search public profiles once'}));await screen.findByRole('heading',{name:candidate.title});fireEvent.change(screen.getByLabelText('Business-profile search'),{target:{value:'Another company search'}});expect(screen.queryByRole('heading',{name:candidate.title})).toBeNull();
});
it('stages source evidence without guessing identity or saving a contact',async()=>{
  localStorage.clear();const db=vi.mocked(accessProspectDatabase);db.mockReset();db.mockResolvedValue({revision:2,workspace:emptyWorkspace()});
  const fetch=vi.fn().mockResolvedValueOnce(response(cap)).mockResolvedValueOnce(response(result));vi.stubGlobal('fetch',fetch);render(<ProspectResearchWorkspace/>);
  await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Check search connection'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));await screen.findByText(/connection configured/);fireEvent.click(screen.getByRole('button',{name:'Search public profiles once'}));fireEvent.click(await screen.findByRole('button',{name:'Use source in prospect form'}));
  expect(screen.getByLabelText('Public source URL (HTTPS)')).toHaveValue(candidate.url);expect(screen.getByLabelText('Full name')).toHaveValue('');expect(screen.getByLabelText('Company')).toHaveValue('');expect((screen.getByLabelText('Evidence of relevance') as HTMLTextAreaElement).value).toContain('unverified');expect(db).toHaveBeenCalledTimes(1);
});
it('preserves an unfinished form unless source replacement is confirmed',async()=>{
  localStorage.clear();const db=vi.mocked(accessProspectDatabase);db.mockReset();db.mockResolvedValue({revision:2,workspace:emptyWorkspace()});
  const fetch=vi.fn().mockResolvedValueOnce(response(cap)).mockResolvedValueOnce(response(result));vi.stubGlobal('fetch',fetch);render(<ProspectResearchWorkspace/>);
  await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Check search connection'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Public source URL (HTTPS)'),{target:{value:'https://example.com/original'}});fireEvent.change(screen.getByLabelText('Company'),{target:{value:'Keep this company'}});
  fireEvent.click(screen.getByRole('button',{name:'Check search connection'}));await screen.findByText(/connection configured/);fireEvent.click(screen.getByRole('button',{name:'Search public profiles once'}));fireEvent.click(await screen.findByRole('button',{name:'Use source in prospect form'}));
  expect(screen.getByLabelText('Public source URL (HTTPS)')).toHaveValue('https://example.com/original');fireEvent.click(screen.getByRole('button',{name:'Replace form source and evidence'}));expect(screen.getByLabelText('Company')).toHaveValue('Keep this company');expect(screen.getByLabelText('Public source URL (HTTPS)')).toHaveValue(candidate.url);expect(db).toHaveBeenCalledTimes(1);
});
