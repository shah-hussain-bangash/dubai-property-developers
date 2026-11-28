import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest} from '@/services/agentKnowledge';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const index={configured:true,agents:[{id:'documents',name:'Document Agent',status:'partial'}]};
beforeEach(()=>{request.mockReset();});
afterEach(()=>{cleanup();vi.useRealTimers();});
it('retries a failed workspace read in place and loads its selected agent only after success',async()=>{let attempts=0;request.mockImplementation(async path=>{if(path===''){if(++attempts===1)throw Error('Fictional offline service');return index;}return {agent_id:'documents',sources:[]};});render(<AgentKnowledgePanel/>);await screen.findByRole('alert');expect(screen.getByRole('button',{name:'Save source for this agent'})).toBeDisabled();expect(screen.queryByText(/No sources for this agent yet/)).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Retry knowledge workspace'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Save source for this agent'})).toBeEnabled());expect(screen.getByLabelText('Agent')).toHaveValue('documents');expect(screen.queryByRole('alert')).toBeNull();expect(request.mock.calls.filter(([path])=>path==='')).toHaveLength(2);expect(request.mock.calls.every(([,init])=>!init?.method)).toBe(true);});
it('times out a stalled workspace request, retries, and discards the late old registry',async()=>{vi.useFakeTimers();let finish!:(v:unknown)=>void;let reads=0;request.mockImplementation(async path=>path===''?++reads===1?new Promise(resolve=>{finish=resolve;}):index:{agent_id:'documents',sources:[]});render(<AgentKnowledgePanel/>);await act(async()=>{});expect(screen.getByText('Loading knowledge workspace…')).toBeVisible();const signal=request.mock.calls[0][2];await act(async()=>vi.advanceTimersByTimeAsync(45000));expect(signal?.aborted).toBe(true);expect(screen.getByRole('alert')).toHaveTextContent('workspace took too long');await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Retry knowledge workspace'})));expect(screen.getByLabelText('Agent')).toHaveValue('documents');await act(async()=>finish({configured:true,agents:[{id:'marketing',name:'Stale Agent'}]}));expect(screen.queryByRole('option',{name:'Stale Agent'})).toBeNull();expect(screen.getByLabelText('Agent')).toHaveValue('documents');});
it('cleans up the registry request and deadline when unmounted',async()=>{vi.useFakeTimers();request.mockImplementation(async()=>new Promise(()=>{}));const view=render(<AgentKnowledgePanel/>);await act(async()=>{});const signal=request.mock.calls[0][2];expect(vi.getTimerCount()).toBeGreaterThan(0);view.unmount();expect(signal?.aborted).toBe(true);expect(vi.getTimerCount()).toBe(0);});
it('shows the explicit empty-registry state without claiming an empty selected source list',async()=>{request.mockResolvedValue({configured:true,agents:[]});render(<AgentKnowledgePanel/>);expect(await screen.findByText('No agents are registered in this workspace.')).toBeVisible();expect(screen.queryByText(/No sources for this agent yet/)).toBeNull();expect(screen.getByRole('button',{name:'Refresh sources'})).toBeDisabled();});
it.each([
 null,
 {configured:true,agents:null},
 {configured:'true',agents:index.agents},
 {...index,agents:[...index.agents,...index.agents]},
 {...index,agents:[{id:'../documents',name:'Fictional invalid agent'}]},
 {...index,agents:[{id:'documents',name:'  '}]},
 {...index,agents:[null]},
])('rejects an unverifiable registry before applying agents %#',async value=>{request.mockResolvedValue(value);render(<AgentKnowledgePanel/>);await screen.findByRole('alert');expect(screen.getByRole('button',{name:'Retry knowledge workspace'})).toBeEnabled();expect(screen.getByRole('button',{name:'Save source for this agent'})).toBeDisabled();expect(screen.getByLabelText('Agent').querySelectorAll('option')).toHaveLength(0);expect(request.mock.calls.every(([path])=>path==='')).toBe(true);expect(screen.queryByText(/No sources for this agent yet/)).toBeNull();});
