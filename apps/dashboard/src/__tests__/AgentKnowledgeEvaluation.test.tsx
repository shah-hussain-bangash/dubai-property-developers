import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,type SourceAnswer} from '@/services/agentKnowledge';
import {parseEvaluationSet,parseEvaluationReport,type EvaluationSet,type EvaluationReport} from '@/services/knowledgeEvaluation';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const checks:EvaluationSet={agent_id:'documents',cases:[{id:'case-1',question:'project gardens',expectation:'answer',expected_excerpt:'eight gardens'}]};
const answer:SourceAnswer={agent_id:'documents',answered:true,supplied_sources_only:true,method:'source-excerpts',sent:false,text:'[1] Fictional project contains eight gardens.',sources:[{source_id:'one',label:'1',title:'Fictional PDF',uri:null,page:2,excerpt:'Fictional project contains eight gardens.'}]};
const report:EvaluationReport={agent_id:'documents',supplied_sources_only:true,sent:false,evaluated:1,passed:1,failed:0,cases:[{id:'case-1',passed:true,answer}]};
beforeEach(()=>{request.mockReset();request.mockImplementation(async(path)=>{if(path==='')return {configured:true,agents:[{id:'documents',name:'Document Agent'},{id:'marketing',name:'Marketing Agent'}]};if(path.endsWith('/evaluate'))return report;return {agent_id:path.split('/')[1],sources:[]};});});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
function blobText(blob:Blob):Promise<string>{return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsText(blob);});}
async function ready(){render(<AgentKnowledgePanel/>);await waitFor(()=>expect(request).toHaveBeenCalledWith('/documents/sources',{},expect.any(AbortSignal)));await waitFor(()=>expect(screen.getByRole('button',{name:'Run saved checks'})).toBeEnabled());}
function fill(){fireEvent.change(screen.getByLabelText('Question 1'),{target:{value:'project gardens'}});fireEvent.change(screen.getByLabelText('Expected passage 1'),{target:{value:'eight gardens'}});}
async function run(){fill();fireEvent.click(screen.getByRole('button',{name:'Run saved checks'}));await screen.findByText('1 of 1 checks passed');}
function load(value:unknown,size=30){const file=new File(['fixture'],'questions.json',{type:'application/json'});Object.defineProperty(file,'text',{value:async()=>JSON.stringify(value)});Object.defineProperty(file,'size',{value:size});fireEvent.change(screen.getByLabelText('Load question set for this agent'),{target:{files:[file]}});}

describe('separate per-agent evaluation data',()=>{
 it('runs read-only checks and shows actual PDF references',async()=>{await ready();await run();expect(screen.getByText('[1] Fictional PDF · Page 2')).toBeVisible();const call=request.mock.calls.find(([path])=>path.endsWith('/evaluate'));expect(call?.[0]).toBe('/documents/evaluate');expect(JSON.parse(call?.[1]?.body as string)).toEqual(checks);expect(request.mock.calls.some(([path,init])=>path.includes('/sources')&&init?.method==='POST')).toBe(false);});
 it('clears results after edits and clears questions when switching agents',async()=>{await ready();await run();fireEvent.change(screen.getByLabelText('Expected passage 1'),{target:{value:'nine gardens'}});expect(screen.queryByText('1 of 1 checks passed')).toBeNull();fireEvent.change(screen.getByLabelText('Agent'),{target:{value:'marketing'}});await screen.findByText('Saved checks for Marketing Agent');expect(screen.getByLabelText('Question 1')).toHaveValue('');});
 it('supports no-answer checks without expected knowledge',async()=>{await ready();fireEvent.change(screen.getByLabelText('Expected outcome 1'),{target:{value:'no_answer'}});expect(screen.queryByLabelText('Expected passage 1')).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Add question'}));expect(screen.getByLabelText('Question 2')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Remove question 2'}));expect(screen.queryByLabelText('Question 2')).toBeNull();});
 it('loads an agent-bound question file without writing sources',async()=>{await ready();load(checks);await waitFor(()=>expect(screen.getByLabelText('Question 1')).toHaveValue('project gardens'));expect(request.mock.calls.some(([,init])=>init?.method==='POST')).toBe(false);});
 it.each(['wrong agent','too large','bad shape'])('rejects %s files while retaining current questions',async reason=>{await ready();fill();load(reason==='wrong agent'?{...checks,agent_id:'marketing'}:reason==='bad shape'?{cases:[]}:checks,reason==='too large'?100001:30);await screen.findByRole('alert');expect(screen.getByLabelText('Question 1')).toHaveValue('project gardens');});
 it('saves question sets and reports with matching agent ownership',async()=>{const blobs:Blob[]=[];vi.spyOn(URL,'createObjectURL').mockImplementation(blob=>{blobs.push(blob as Blob);return 'blob:fixture';});vi.spyOn(URL,'revokeObjectURL').mockImplementation(()=>{});const clicks=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});await ready();await run();fireEvent.click(screen.getByRole('button',{name:'Save question set'}));fireEvent.click(screen.getByRole('button',{name:'Download results'}));expect(clicks).toHaveBeenCalledTimes(2);expect(JSON.parse(await blobText(blobs[0]))).toEqual(checks);expect(JSON.parse(await blobText(blobs[1]))).toEqual({questions:checks,results:report});});
 it('locks agent selection during a run and rejects an unverified result',async()=>{let finish!:(value:unknown)=>void;request.mockImplementation(async path=>{if(path==='')return {configured:true,agents:[{id:'documents',name:'Document Agent'}]};if(path.endsWith('/evaluate'))return new Promise(resolve=>{finish=resolve;});return {agent_id:'documents',sources:[]};});await ready();fill();fireEvent.click(screen.getByRole('button',{name:'Run saved checks'}));await waitFor(()=>expect(screen.getByLabelText('Agent')).toBeDisabled());finish({...report,agent_id:'marketing'});await screen.findByRole('alert');expect(screen.queryByText('1 of 1 checks passed')).toBeNull();});
 it.each([
  {...report,passed:0},
  {...report,cases:[{...report.cases[0],passed:false}]},
  {...report,cases:[{...report.cases[0],answer:{...answer,text:'Invented reply'}}]},
  {...report,cases:[{...report.cases[0],id:'unexpected'}]},
  {...report,sent:true},
 ])('refuses forged result counts, claims or citations %#',value=>{expect(()=>parseEvaluationReport(value as EvaluationReport,checks)).toThrow();});
 it.each([
  {...checks,cases:[...checks.cases,...checks.cases]},
  {...checks,cases:[{...checks.cases[0],expected_excerpt:'  '}]},
  {...checks,cases:[{...checks.cases[0],expectation:'no_answer'}]},
  {...checks,tenant_id:'foreign'},
 ])('refuses invalid question files %#',value=>{expect(()=>parseEvaluationSet(value,'documents')).toThrow();});
});
