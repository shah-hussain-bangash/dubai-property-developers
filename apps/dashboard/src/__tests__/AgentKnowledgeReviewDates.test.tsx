import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {AgentKnowledgePanel} from '@/features/knowledge/AgentKnowledgePanel';
import {knowledgeRequest,type AssignedSource} from '@/services/agentKnowledge';
vi.mock('@/services/agentKnowledge',async original=>({...await original<typeof import('@/services/agentKnowledge')>(),knowledgeRequest:vi.fn()}));
const request=vi.mocked(knowledgeRequest);
let sources:AssignedSource[];
beforeEach(()=>{sources=[];request.mockReset();request.mockImplementation(async(path,init)=>{if(path==='')return {configured:true,agents:[{id:'documents',name:'Document Agent'},{id:'marketing',name:'Marketing Agent'}]};if (init?.method === 'POST') {
      const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
      const query = new URLSearchParams(path.split('?')[1] ?? '');
      const mime = (init.headers as Record<string,string>)?.['Content-Type'];
      return { agent_id: path.split('/')[1], source: {
        id: 'fixture', title: body.title ?? query.get('title') ?? 'Fictional source',
        kind: body.kind ?? (mime === 'application/pdf' ? 'pdf' : mime === 'text/markdown' ? 'markdown' : 'text'),
        uri: body.kind === 'website' ? body.url : null, chars: 40,
        created: '2026-11-26T00:00:00Z', review_by: body.review_by ?? query.get('review_by') ?? null,
        customer_safe: (body.customer_safe ?? (query.get('customer_safe') === 'true')) ? 1 : 0,
      } };
    }return {agent_id:path.split('/')[1],sources};});});
afterEach(cleanup);
async function ready(){render(<AgentKnowledgePanel/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Save source for this agent'})).toBeEnabled());}
function setDate(value='2030-01-02'){fireEvent.change(screen.getByLabelText('Review by (optional)'),{target:{value}});}
function submit(){fireEvent.submit(screen.getByRole('button',{name:'Save source for this agent'}).closest('form')!);}
function fill(mode:string){fireEvent.change(screen.getByLabelText('Add from'),{target:{value:mode}});fireEvent.change(screen.getByLabelText('Source title'),{target:{value:'Fictional dated guide'}});if(mode==='file')fireEvent.change(screen.getByLabelText('Choose a file'),{target:{files:[new File(['Fictional gardens'],'fixture.md',{type:'text/markdown'})]}});if(mode==='website')fireEvent.change(screen.getByLabelText('Public website link'),{target:{value:'https://example.test/guide'}});if(mode==='text')fireEvent.change(screen.getByLabelText('Source text'),{target:{value:'Fictional garden policy.'}});}
describe('review deadlines on every import method',()=>{
 it.each(['file','website','text'])('saves a %s deadline for only the selected agent and resets the successful draft',async mode=>{await ready();fill(mode);setDate();fireEvent.click(screen.getByRole('checkbox'));submit();await screen.findByText(/Source saved for Document Agent/);const [path,options]=request.mock.calls.find(([,init])=>init?.method==='POST')!;if(mode==='file'){expect(path).toBe('/documents/sources?title=Fictional%20dated%20guide&customer_safe=true&review_by=2030-01-02');expect(options?.body).toBeInstanceOf(File);}else{expect(path).toBe('/documents/sources');expect(JSON.parse(options?.body as string)).toMatchObject({review_by:'2030-01-02',kind:mode,customer_safe:true});}expect(screen.getByLabelText('Review by (optional)')).toHaveValue('');expect(screen.getByRole('checkbox')).not.toBeChecked();});
 it('clears customer approval whenever the date is changed or cleared',async()=>{await ready();fireEvent.click(screen.getByRole('checkbox'));setDate();expect(screen.getByRole('checkbox')).not.toBeChecked();fireEvent.click(screen.getByRole('checkbox'));setDate('');expect(screen.getByRole('checkbox')).not.toBeChecked();});
 it('clears the deadline when switching to another agent',async()=>{await ready();setDate();fireEvent.change(screen.getByLabelText('Agent'),{target:{value:'marketing'}});await screen.findByText('Add knowledge for Marketing Agent');expect(screen.getByLabelText('Review by (optional)')).toHaveValue('');});
 it('retains the date and draft after a rejected upload',async()=>{await ready();fill('text');setDate();request.mockRejectedValueOnce(Error('Choose a review date that is today or later.'));submit();expect(await screen.findByRole('alert')).toHaveTextContent('Choose a review date');expect(screen.getByLabelText('Review by (optional)')).toHaveValue('2030-01-02');expect(screen.getByLabelText('Source text')).toHaveValue('Fictional garden policy.');});
 it('shows existing source deadlines separately from sources without one',async()=>{sources=[{id:'one',title:'Dated fixture',kind:'pdf',uri:null,chars:40,created:'2026-11-26',review_by:'2030-01-02',customer_safe:0},{id:'two',title:'Undated fixture',kind:'text',uri:null,chars:40,created:'2026-11-26',review_by:null,customer_safe:0}];await ready();expect(screen.getByText('2030-01-02')).toHaveAttribute('datetime','2030-01-02');expect(screen.getByText('No review deadline')).toBeVisible();expect(screen.getByText(/Leaving this blank preserves an existing deadline/)).toBeVisible();});
});
