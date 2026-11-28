import React,{Component,type ReactNode} from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,parseSourceList} from '@/services/agentKnowledge';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
const index={configured:true,agents:[{id:'documents',name:'Document Agent',status:'partial'}]};
const source={id:'fictional-source',title:'Fictional preserved source',kind:'text',uri:null,chars:40,created:'2026-11-26T00:00:00Z',review_by:null,customer_safe:0};
class Boundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<p role="alert">Fictional rendering crash</p>:this.props.children;}}
beforeEach(()=>{request.mockReset();vi.spyOn(console,'error').mockImplementation(()=>{});});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
function show(){render(<Boundary><AgentKnowledgePanel/></Boundary>);}
it('rejects a malformed initial list without crashing and offers a read retry',async()=>{request.mockImplementation(async path=>path===''?index:{agent_id:'documents',sources:null});show();await screen.findByRole('alert');expect(screen.queryByText('Fictional rendering crash')).toBeNull();expect(screen.getByRole('button',{name:'Save source for this agent'})).toBeDisabled();expect(screen.getByRole('button',{name:'Refresh sources'})).toBeEnabled();expect(screen.queryByText(/No sources for this agent yet/)).toBeNull();});
it('retains the last valid list when a refresh returns malformed data',async()=>{let reads=0;request.mockImplementation(async path=>path===''?index:{agent_id:'documents',sources:++reads===1?[source]:[null]});show();await screen.findByText(source.title);fireEvent.click(screen.getByRole('button',{name:'Refresh sources'}));await screen.findByRole('alert');expect(screen.queryByText('Fictional rendering crash')).toBeNull();expect(screen.getByText(source.title)).toBeVisible();expect(screen.getByRole('button',{name:'Refresh sources'})).toBeEnabled();});
it('retains acknowledged-save notice and retries only a read after malformed refresh',async()=>{let reads=0;request.mockImplementation(async(path,init)=>{if(path==='')return index;if(init?.method==='POST')return {agent_id:'documents',source};reads++;return {agent_id:'documents',sources:reads===1?[]:reads===2?{}:[source]};});show();await waitFor(()=>expect(screen.getByRole('button',{name:'Save source for this agent'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Add from'),{target:{value:'text'}});fireEvent.change(screen.getByLabelText('Source title'),{target:{value:'Fictional new source'}});fireEvent.change(screen.getByLabelText('Source text'),{target:{value:'Fictional source text.'}});fireEvent.click(screen.getByRole('button',{name:'Save source for this agent'}));await screen.findByRole('alert');expect(screen.queryByText('Fictional rendering crash')).toBeNull();expect(screen.getByText(/Source saved for Document Agent/)).toBeVisible();expect(screen.getByRole('alert')).toHaveTextContent('Source was saved, but the list could not be refreshed');expect(screen.getByLabelText('Source title')).toHaveValue('');fireEvent.click(screen.getByRole('button',{name:'Refresh sources'}));await screen.findByText(source.title);expect(request.mock.calls.filter(([,init])=>init?.method==='POST')).toHaveLength(1);});
it.each([
 null,
 {agent_id:'documents',sources:{}},
 {agent_id:'marketing',sources:[source]},
 {agent_id:'documents',sources:[source,source]},
 {agent_id:'documents',sources:Array(101).fill(source)},
 ...[
  {id:'../source'}, {title:null}, {title:'  '}, {kind:null}, {kind:'unknown'},
  {chars:null}, {chars:0}, {chars:1.5}, {chars:200001},
  {customer_safe:true}, {customer_safe:'1'}, {created:'unknown'},
  {review_by:'2030-02-30'}, {review_by:undefined}, {uri:'javascript:alert(1)'},
 ].map(patch=>({agent_id:'documents',sources:[{...source,...patch}]})),
 {agent_id:'documents',sources:Array.from({length:11},(_,i)=>({...source,id:'fictional-'+i,chars:200000}))},
])('rejects malformed lists, metadata and limits before state application %#',value=>{expect(()=>parseSourceList(value,'documents')).toThrow();});
it('preserves valid metadata and accepts an empty owned list without rewriting values',()=>{const value={agent_id:'documents',sources:[{...source,title:'Fictional 🌴 دبي',uri:'HTTPS://EXAMPLE.TEST/fictional',chars:200000,review_by:'2030-01-01',customer_safe:1}]};expect(parseSourceList(value,'documents')).toEqual(value.sources);expect(parseSourceList({agent_id:'documents',sources:[]},'documents')).toEqual([]);});
