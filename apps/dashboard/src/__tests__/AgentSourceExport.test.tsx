import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,type AssignedSource} from '@/services/agentKnowledge';
import {parseSourceExport,type SourceExport} from '@/services/sourceExport';
import {parseEvaluationSet} from '@/services/knowledgeEvaluation';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const text='Fictional 🌴 دبي policy.';
const source:AssignedSource={id:'a'.repeat(64),title:'Fictional PDF',kind:'pdf',uri:null,chars:[...text].length,created:'2026-11-26T10:00:00+00:00',review_by:'2030-01-02',customer_safe:0};
const record:SourceExport={format:'agent-source-text-v1',agent_id:'documents',exported_at:'2026-11-26T11:00:00.123456+00:00',sources:[{source,pages:[{page:1,text:''},{page:2,text}]}]};
let blobs:Blob[],filenames:string[];
beforeEach(()=>{blobs=[];filenames=[];request.mockReset();request.mockImplementation(async path=>path===''?{configured:true,agents:[{id:'documents',name:'Document Agent'},{id:'marketing',name:'Marketing Agent'}]}:path.endsWith('/export')?record:{agent_id:path.split('/')[1],sources:[source]});vi.spyOn(URL,'createObjectURL').mockImplementation(blob=>{blobs.push(blob as Blob);return 'blob:fictional-export';});vi.spyOn(URL,'revokeObjectURL').mockImplementation(()=>{});vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){filenames.push(this.download);});});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
async function ready(){render(<AgentKnowledgePanel/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Download saved knowledge'})).toBeEnabled());}
function download(){fireEvent.click(screen.getByRole('button',{name:'Download saved knowledge'}));}
function blobText(blob:Blob):Promise<string>{return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsText(blob);});}
describe('selected-agent saved text download',()=>{
 it('downloads exact validated Unicode/pages/metadata without writes or changing drafts',async()=>{await ready();fireEvent.change(screen.getByLabelText('Source title'),{target:{value:'Unsaved fixture'}});download();await screen.findByText(/Saved knowledge download prepared/);expect(filenames).toEqual(['documents-saved-knowledge.json']);expect(JSON.parse(await blobText(blobs[0]))).toEqual(record);expect(blobs[0].type).toBe('application/json');expect(screen.getByLabelText('Source title')).toHaveValue('Unsaved fixture');expect(request).toHaveBeenCalledWith('/documents/export',{},expect.any(AbortSignal));expect(request.mock.calls.some(([,init])=>['POST','PATCH','DELETE'].includes(init?.method??''))).toBe(false);});
 it('blocks agent changes during export and routes the next export to the newly selected agent',async()=>{let finish!:(v:unknown)=>void;const base=request.getMockImplementation()!;request.mockImplementation((path,init,signal)=>path==='/documents/export'?new Promise(resolve=>{finish=resolve;}):base(path,init,signal));await ready();download();await waitFor(()=>expect(screen.getByLabelText('Agent')).toBeDisabled());await act(async()=>finish(record));fireEvent.change(screen.getByLabelText('Agent'),{target:{value:'marketing'}});await waitFor(()=>expect(screen.getByRole('button',{name:'Download saved knowledge'})).toBeEnabled());request.mockResolvedValueOnce({...record,agent_id:'marketing'});download();await waitFor(()=>expect(filenames).toEqual(['documents-saved-knowledge.json','marketing-saved-knowledge.json']));});
 it('shows failures without creating a file and supports a fresh retry',async()=>{await ready();request.mockRejectedValueOnce(Error('Fictional connection failed'));download();await screen.findByText('Fictional connection failed');expect(blobs).toHaveLength(0);download();await screen.findByText(/Saved knowledge download prepared/);expect(blobs).toHaveLength(1);});
 it('rejects another agent response before downloading',async()=>{await ready();request.mockResolvedValueOnce({...record,agent_id:'marketing'});download();await screen.findByRole('alert');expect(blobs).toHaveLength(0);});
 it('does not download a late response after unmount',async()=>{let finish!:(v:unknown)=>void;const base=request.getMockImplementation()!;request.mockImplementation((path,init,signal)=>path.endsWith('/export')?new Promise(resolve=>{finish=resolve;}):base(path,init,signal));const view=render(<AgentKnowledgePanel/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Download saved knowledge'})).toBeEnabled());download();view.unmount();await act(async()=>finish(record));expect(blobs).toHaveLength(0);});
 it('supports an empty manifest and keeps exports separate from question files',()=>{expect(parseSourceExport({...record,sources:[]},'documents').sources).toEqual([]);expect(()=>parseEvaluationSet(record,'documents')).toThrow();});
 it.each([
  {...record,format:'unknown'},
  {...record,agent_id:'marketing'},
  {...record,exported_at:'2030-02-30T10:00:00Z'},
  {...record,exported_at:'missing time'},
  {...record,sources:[...record.sources,...record.sources]},
  {...record,sources:Array(101).fill(record.sources[0])},
  {...record,sources:[{...record.sources[0],source:{...source,customer_safe:true}}]},
  {...record,sources:[{...record.sources[0],source:{...source,review_by:'2030-02-30'}}]},
  {...record,sources:[{...record.sources[0],source:{...source,chars:999}}]},
  {...record,sources:[{...record.sources[0],pages:[{page:3,text}]}]},
  {...record,sources:[{...record.sources[0],source:{...source,uri:'javascript:alert(1)'}}]},
 ])('refuses unverified format, owner, dates, counts or page references %#',value=>{expect(()=>parseSourceExport(value as SourceExport,'documents')).toThrow();});
});
