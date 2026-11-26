import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,parseSourcePreview,type AssignedSource,type SourcePreview} from '@/services/agentKnowledge';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const source:AssignedSource={id:'fixture',title:'Fictional PDF',kind:'pdf',uri:null,chars:23,created:'2026-11-26',review_by:'2030-01-02',customer_safe:0};
const preview:SourcePreview={agent_id:'documents',source,pages:[{page:1,text:''},{page:2,text:'Fictional gardens text.'}]};
beforeEach(()=>{request.mockReset();request.mockImplementation(async path=>path===''?{configured:true,agents:[{id:'documents',name:'Document Agent'},{id:'marketing',name:'Marketing Agent'}]}:path.endsWith('/fixture')?preview:{agent_id:path.split('/')[1],sources:[source]});});
afterEach(cleanup);
async function ready(){render(<AgentKnowledgePanel/>);await waitFor(()=>expect(screen.getByRole('button',{name:'View saved text: Fictional PDF'})).toBeEnabled());}
async function open(){fireEvent.click(screen.getByRole('button',{name:'View saved text: Fictional PDF'}));await screen.findByRole('heading',{name:'Saved text: Fictional PDF'});}
describe('saved extracted text review',()=>{
 it('shows PDF pages including empty ones without mutating knowledge',async()=>{await ready();await open();expect(screen.getByRole('heading',{name:'Page 2'})).toBeVisible();expect(screen.getByText('Fictional gardens text.')).toBeVisible();expect(screen.getByText('No readable text on this page.')).toBeVisible();expect(request).toHaveBeenCalledWith('/documents/sources/fixture',{},expect.any(AbortSignal));expect(request.mock.calls.some(([,init])=>init?.method==='POST'||init?.method==='DELETE')).toBe(false);fireEvent.click(screen.getByRole('button',{name:'Close saved text'}));expect(screen.queryByText('Fictional gardens text.')).toBeNull();});
 it('clears the preview when selecting another agent',async()=>{await ready();await open();fireEvent.change(screen.getByLabelText('Agent'),{target:{value:'marketing'}});await screen.findByText('Add knowledge for Marketing Agent');expect(screen.queryByText('Fictional gardens text.')).toBeNull();});
 it('clears old text on refresh and shows a bounded failed-read message',async()=>{await ready();await open();fireEvent.click(screen.getByRole('button',{name:'Refresh sources'}));await waitFor(()=>expect(screen.queryByText('Fictional gardens text.')).toBeNull());request.mockRejectedValueOnce(Error('Source not found in this agent\'s knowledge.'));fireEvent.click(screen.getByRole('button',{name:'View saved text: Fictional PDF'}));expect(await screen.findByRole('alert')).toHaveTextContent('Source not found');});
 it('renders supplied markup as plain text',async()=>{const text='<script>do not execute</script>';request.mockImplementation(async path=>path===''?{configured:true,agents:[{id:'documents',name:'Document Agent'}]}:path.endsWith('/fixture')?{...preview,source:{...source,chars:text.length},pages:[{page:1,text}]}:{agent_id:'documents',sources:[source]});await ready();await open();expect(screen.getByText(text)).toBeVisible();expect(document.querySelector('script')).toBeNull();});
 it.each([
  {...preview,agent_id:'marketing'},
  {...preview,source:{...source,id:'other'}},
  {...preview,source:{...source,chars:999}},
  {...preview,pages:[{page:3,text:'Fictional gardens text.'}]},
  {...preview,source:{...source,uri:'javascript:alert(1)'}},
  {...preview,pages:[]},
 ])('rejects incorrect ownership, pages or content metadata %#',value=>{expect(()=>parseSourcePreview(value,'documents','fixture')).toThrow();});
 it('counts Unicode code points like the backend',()=>{const value={...preview,source:{...source,chars:2},pages:[{page:1,text:'🌴د'}]};expect(parseSourcePreview(value,'documents','fixture')).toEqual(value);});
});
