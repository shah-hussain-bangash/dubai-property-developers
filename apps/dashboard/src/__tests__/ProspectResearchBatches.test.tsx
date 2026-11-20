import { cleanup,fireEvent,render,screen } from '@testing-library/react';
import { afterEach,expect,it,vi } from 'vitest';
import type { SavedBatch } from '@/services/prospectBatches';
import { ProspectResearchBatches } from '@/features/prospects/ProspectResearchBatches';
const state:SavedBatch['state']={id:'test-job',target:500,status:'ready',cursor:0,provider_attempts:0,resume_at:null,notice:'Created without a search.',queries:[{query:'Dubai CEO public profile',role:'ceo',scope:'linkedin'}],candidates:[]};
const envelope=(s:SavedBatch['state']=state,revision=1)=>({storage:'postgresql',scheduled:false,outreach_enabled:false,batch:{revision,state:s}});
const response=(value:unknown,status=200)=>({ok:status===200,status,text:async()=>JSON.stringify(value)});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
async function create(){fireEvent.click(screen.getByRole('button',{name:'Create research job - no search'}));await screen.findByRole('heading',{name:'Research job test-job'});}
it('does not load or search automatically on mount',()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);expect(fetch).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'Run next query - uses search credit'})).toBeNull();
});
it('creates a plan with one explicit local POST and no advance',async()=>{
  const fetch=vi.fn().mockResolvedValue(response(envelope()));vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);await create();expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toMatch(/\/batches$/);expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({location:'Dubai',scope:'linkedin',target:500});expect(fetch.mock.calls[0][1].credentials).toBe('omit');
});
it('sends one revisioned advance despite a second click',async()=>{
  let finish!:(value:unknown)=>void;
  const fetch=vi.fn().mockResolvedValueOnce(response(envelope())).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);await create();const button=screen.getByRole('button',{name:'Run next query - uses search credit'});fireEvent.click(button);fireEvent.click(button);expect(fetch).toHaveBeenCalledTimes(2);expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({action:'advance',revision:1});finish(response(envelope()));await vi.waitFor(()=>expect(button).toBeEnabled());
});
it('requires reload after an uncertain failed action and never retries it',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response(envelope())).mockResolvedValueOnce(response({},409)).mockResolvedValueOnce(response(envelope(state,2)));vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);await create();fireEvent.click(screen.getByRole('button',{name:'Run next query - uses search credit'}));await screen.findByRole('alert');expect(screen.getByRole('button',{name:'Run next query - uses search credit'})).toBeDisabled();expect(fetch).toHaveBeenCalledTimes(2);fireEvent.click(screen.getByRole('button',{name:'Reload selected job'}));await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Run next query - uses search credit'})).toBeEnabled());expect(fetch.mock.calls[2][1].method).toBe('GET');
});
it('does not offer a quota-wait advance before the resume time',async()=>{
  const waiting={...state,status:'quota_wait',resume_at:new Date(Date.now()+86400000).toISOString()};const fetch=vi.fn().mockResolvedValue(response(envelope(waiting as typeof state)));vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);await create();expect(screen.getByRole('button',{name:'Run next query - uses search credit'})).toBeDisabled();expect(screen.getByText(/Quota wait until/)).toBeVisible();expect(fetch).toHaveBeenCalledTimes(1);
});
it('pauses and resumes using updated saved revisions',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response(envelope())).mockResolvedValueOnce(response(envelope({...state,status:'paused'},2))).mockResolvedValueOnce(response(envelope(state,3)));vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);await create();fireEvent.click(screen.getByRole('button',{name:'Pause research job'}));fireEvent.click(await screen.findByRole('button',{name:'Resume research job'}));await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Pause research job'})).toBeEnabled());expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({action:'resume',revision:2});
});
it('rejects an unexpected outreach-enabled response',async()=>{
  const fetch=vi.fn().mockResolvedValue(response({...envelope(),outreach_enabled:true}));vi.stubGlobal('fetch',fetch);render(<ProspectResearchBatches disabled={false} onChoose={vi.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Create research job - no search'}));expect(await screen.findByRole('alert')).toHaveTextContent('provenance');expect(screen.queryByRole('heading',{name:'Research job test-job'})).toBeNull();
});
it('offers a selected public source for review without creating a prospect',async()=>{
  const candidate={id:'1234567890abcdef12345678',title:'Public example profile',url:'https://www.linkedin.com/in/example',snippet:'Public business source',query_role:'ceo',search_query:'Dubai CEO public profile',discovered_at:new Date().toISOString()};
  const fetch=vi.fn().mockResolvedValue(response(envelope({...state,candidates:[candidate]} as unknown as typeof state)));vi.stubGlobal('fetch',fetch);const choose=vi.fn();render(<ProspectResearchBatches disabled={false} onChoose={choose}/>);await create();fireEvent.click(screen.getByRole('button',{name:'Review batch source in prospect form'}));expect(choose).toHaveBeenCalledWith(candidate);expect(fetch).toHaveBeenCalledTimes(1);
});
