import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgeCoverage} from '@/features/knowledge/AgentKnowledgeCoverage';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,type KnowledgeAgent} from '@/services/agentKnowledge';
import {parseKnowledgeCoverage,type KnowledgeCoverage} from '@/services/knowledgeCoverage';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const agents:KnowledgeAgent[]=[{id:'documents',name:'Document Agent',status:'functional'},{id:'marketing',name:'Marketing Agent',status:'partial'}];
const zero={total:0,staff_eligible:0,customer_eligible:0,overdue:0,due_soon:0,undated:0};
const counts={total:5,staff_eligible:4,customer_eligible:2,overdue:1,due_soon:2,undated:1};
const report:KnowledgeCoverage={as_of:'2030-01-03',window_days:7,agents:[{agent_id:'documents',...counts},{agent_id:'marketing',...zero}],summary:counts};
beforeEach(()=>{request.mockReset();request.mockResolvedValue(report);});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.useRealTimers();});
function show(disabled=false){const onSelect=vi.fn();render(<AgentKnowledgeCoverage agents={agents} disabled={disabled} onSelect={onSelect}/>);return onSelect;}
function check(){fireEvent.click(screen.getByRole('button',{name:'Check all agents’ sources'}));}
describe('organization agent source coverage',()=>{
 it('loads only on demand, shows current counts and selects the correct agent',async()=>{const select=show();expect(request).not.toHaveBeenCalled();check();await screen.findByText('5 saved sources · 2 current customer-approved · 1 overdue');expect(screen.getByText('No sources assigned')).toBeVisible();expect(screen.getByText('Checked for 2030-01-03 · Server calendar day')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Open knowledge: Marketing Agent'}));expect(select).toHaveBeenCalledWith('marketing');expect(request).toHaveBeenCalledWith('/coverage',{},expect.any(AbortSignal));});
 it('honors disabled workspace controls',()=>{show(true);expect(screen.getByRole('button',{name:'Check all agents’ sources'})).toBeDisabled();});
 it('clears old counts before a refresh and retries a failed request',async()=>{show();check();await screen.findByText('No sources assigned');request.mockRejectedValueOnce(Error('Fixture connection failed'));fireEvent.click(screen.getByRole('button',{name:'Refresh agent overview'}));await screen.findByText('Fixture connection failed');expect(screen.queryByText('No sources assigned')).toBeNull();check();await screen.findByText('No sources assigned');expect(screen.queryByRole('alert')).toBeNull();});
 it('cancels an unfinished request on unmount',async()=>{request.mockImplementation((_p,_i,signal)=>new Promise((_resolve,reject)=>signal?.addEventListener('abort',()=>reject(Error('cancelled')))));const view=render(<AgentKnowledgeCoverage agents={agents} disabled={false} onSelect={vi.fn()}/>);check();expect(screen.getByRole('button',{name:'Checking agent sources…'})).toBeDisabled();const signal=request.mock.calls[0][2];view.unmount();expect(signal?.aborted).toBe(true);});
 it('times out with a retry action',async()=>{vi.useFakeTimers();request.mockImplementation((_p,_i,signal)=>new Promise((_resolve,reject)=>signal?.addEventListener('abort',()=>reject(Error('cancelled')))));show();check();await act(async()=>vi.advanceTimersByTimeAsync(45000));expect(screen.getByRole('alert')).toHaveTextContent('The source overview did not finish');expect(screen.getByRole('button',{name:'Check all agents’ sources'})).toBeEnabled();});
 it('opens another agent through the panel and clears unsaved approval and coverage',async()=>{request.mockImplementation(async path=>path===''?{configured:true,agents}:path==='/coverage'?report:{agent_id:path.split('/')[1],sources:[]});render(<AgentKnowledgePanel/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Check all agents’ sources'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Source title'),{target:{value:'Unsaved fixture'}});fireEvent.click(screen.getByLabelText('Allow this source in customer-facing answers'));check();await screen.findByText('No sources assigned');fireEvent.click(screen.getByRole('button',{name:'Open knowledge: Marketing Agent'}));await waitFor(()=>expect(request).toHaveBeenCalledWith('/marketing/sources',{},expect.any(AbortSignal)));expect(screen.getByLabelText('Agent')).toHaveValue('marketing');expect(screen.getByLabelText('Source title')).toHaveValue('');expect(screen.getByLabelText('Allow this source in customer-facing answers')).not.toBeChecked();expect(screen.queryByText('No sources assigned')).toBeNull();});
 it.each([
  {...report,as_of:'2030-02-30'},
  {...report,agents:report.agents.slice(1)},
  {...report,agents:[report.agents[1],report.agents[0]]},
  {...report,agents:[{...report.agents[0],customer_eligible:5},report.agents[1]]},
  {...report,summary:{...counts,total:6}},
  {...report,agents:[{...report.agents[0],total:true},report.agents[1]]},
  {...report,agents:[{...report.agents[0],undated:4},report.agents[1]]},
  {...report,window_days:14},
 ])('rejects unverifiable dates, owners or counts %#',value=>{expect(()=>parseKnowledgeCoverage(value as KnowledgeCoverage,agents)).toThrow();});
 it('suppresses unverified counts in the page',async()=>{request.mockResolvedValue({...report,summary:{...counts,total:900}});show();check();await screen.findByRole('alert');expect(screen.queryByText('No sources assigned')).toBeNull();});
});
