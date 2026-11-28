import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,type AssignedSource} from '@/services/agentKnowledge';
import {parseReviewQueue,type ReviewQueue} from '@/services/sourceReviewQueue';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const source:AssignedSource={id:'fixture',title:'Fictional overdue PDF',kind:'pdf',uri:null,chars:23,created:'2026-11-26',review_by:'2030-01-02',customer_safe:0};
const queue:ReviewQueue={agent_id:'documents',as_of:'2030-01-03',window_days:7,summary:{overdue:1,due_soon:0,current:0,undated:0},items:[{...source,review_status:'overdue'}]};
beforeEach(()=>{request.mockReset();request.mockImplementation(async path=>path===''?{configured:true,agents:[{id:'documents',name:'Document Agent'},{id:'marketing',name:'Marketing Agent'}]}:path.endsWith('/review-queue')?queue:path.endsWith('/fixture')?{agent_id:'documents',source,pages:[{page:1,text:'Fictional gardens text.'}]}:{agent_id:path.split('/')[1],sources:[source]});});
afterEach(()=>{cleanup();vi.useRealTimers();});
async function ready(){render(<AgentKnowledgePanel/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Check review dates'})).toBeEnabled());}
async function check(){fireEvent.click(screen.getByRole('button',{name:'Check review dates'}));await screen.findByText('Checked for 2030-01-03 · Server calendar day');}
describe('selected-agent review queue',()=>{
 it('checks only on request and opens the owned saved text for review',async()=>{await ready();expect(request.mock.calls.some(([path])=>path.endsWith('/review-queue'))).toBe(false);await check();expect(screen.getByText('1 overdue · 0 due soon · 0 current · 0 without a review date')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Review source: Fictional overdue PDF'}));expect(await screen.findByRole('heading',{name:'Saved text: Fictional overdue PDF'})).toBeVisible();expect(request).toHaveBeenCalledWith('/documents/sources/fixture',{},expect.any(AbortSignal));expect(request.mock.calls.some(([,init])=>init?.method==='PATCH'||init?.method==='POST')).toBe(false);});
 it('shows an empty action list without claiming undated sources expire',async()=>{await ready();request.mockResolvedValueOnce({...queue,summary:{overdue:0,due_soon:0,current:2,undated:1},items:[]});fireEvent.click(screen.getByRole('button',{name:'Check review dates'}));expect(await screen.findByText('No dated sources need review in this window.')).toBeVisible();expect(screen.getByText(/Undated sources have no automatic cutoff/)).toBeVisible();});
 it('clears old results on refresh failure and permits retry',async()=>{await ready();await check();request.mockRejectedValueOnce(Error('Fictional date check failure'));fireEvent.click(screen.getByRole('button',{name:'Refresh review dates'}));expect(await screen.findByRole('alert')).toHaveTextContent('Fictional date check failure');expect(screen.queryByRole('button',{name:'Review source: Fictional overdue PDF'})).toBeNull();await check();});
 it('aborts a late result when the selected agent changes',async()=>{await ready();let finish!:(value:unknown)=>void;request.mockImplementationOnce(async()=>new Promise(resolve=>{finish=resolve;}));fireEvent.click(screen.getByRole('button',{name:'Check review dates'}));const signal=request.mock.calls.at(-1)?.[2];fireEvent.change(screen.getByLabelText('Agent'),{target:{value:'marketing'}});await screen.findByText('Add knowledge for Marketing Agent');expect(signal?.aborted).toBe(true);await act(async()=>finish(queue));expect(screen.queryByText('Checked for 2030-01-03 · Server calendar day')).toBeNull();});
 it('clears a result when saved source metadata changes',async()=>{await ready();await check();request.mockResolvedValueOnce({agent_id:'documents',sources:[{...source,review_by:'2030-02-01'}]});fireEvent.click(screen.getByRole('button',{name:'Refresh sources'}));await waitFor(()=>expect(screen.queryByText('Checked for 2030-01-03 · Server calendar day')).toBeNull());expect(screen.getByRole('button',{name:'Check review dates'})).toBeEnabled();});
 it('permits retry after timeout',async()=>{await ready();vi.useFakeTimers();request.mockImplementationOnce(async(_p,_i,signal)=>new Promise((_resolve,reject)=>signal?.addEventListener('abort',()=>reject(Error('aborted')))));fireEvent.click(screen.getByRole('button',{name:'Check review dates'}));await act(async()=>{await vi.advanceTimersByTimeAsync(45000);});expect(screen.getByRole('alert')).toHaveTextContent('The review-date check did not finish');expect(screen.getByRole('button',{name:'Check review dates'})).toBeEnabled();});
 it.each([
  {...queue,agent_id:'marketing'},
  {...queue,as_of:'bad'},
  {...queue,window_days:30},
  {...queue,summary:{...queue.summary,overdue:2}},
  {...queue,summary:{...queue.summary,current:-1}},
  {...queue,items:[{...queue.items[0],review_status:'due_soon'}]},
  {...queue,items:[{...queue.items[0],review_by:'2030-01-11'}]},
  {...queue,items:[{...queue.items[0],review_by:null}]},
 ])('rejects wrong ownership, counts, dates or classifications %#',value=>{expect(()=>parseReviewQueue(value as ReviewQueue,'documents')).toThrow();});
 it('accepts today and the seventh day as due soon using the response date',()=>{for(const review_by of ['2030-01-03','2030-01-10']){const value={...queue,summary:{overdue:0,due_soon:1,current:0,undated:0},items:[{...source,review_by,review_status:'due_soon' as const}]};expect(parseReviewQueue(value,'documents')).toEqual(value);}});
});
