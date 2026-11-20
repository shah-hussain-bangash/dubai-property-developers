import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DemoKnowledgeForm } from '@/features/knowledge/DemoKnowledgeForm';
import { DemoReplyForm } from '@/features/conversations/DemoReplyForm';
const capability = { enabled: true, mock_integrations: true, memory_storage: true };
const citation = { document_id: 'demo-org:demo-plan:v1', title: 'Demo Plan (Fictional)', version: 1, excerpt: 'Fictional source passage.' };
const knowledge = { dev_only: true, uses_mock_integrations: true, source: 'fictional-demo-corpus', status: 'pending_approval', output: { needs_human: false, answer: 'Earlier fictional knowledge answer', notes: [], citations: [citation] } };
const reply = { dev_only: true, uses_mock_integrations: true, source: 'fictional-sales-demo', status: 'pending_approval', sent: false, requires_approval: true, channel: 'web_chat', needs_human: false, handoff_reason: null, intent: 'payment_plan', language: 'en', draft: 'Earlier fictional sales draft', citations: [citation] };
const response = (body: unknown) => ({ ok: true, json: async () => body } as Response);
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
const panels = [
  {name:'knowledge', Component:DemoKnowledgeForm,label:'Question about demo documents',button:'Ask demo question',body:knowledge,text:'Earlier fictional knowledge answer',notice:/Question changed/,key:'question'},
  {name:'sales', Component:DemoReplyForm,label:'Message from a fictional customer',button:'Prepare demo reply',body:reply,text:'Earlier fictional sales draft',notice:/Message changed/,key:'message'},
];
for (const p of panels) describe(p.name+' draft freshness',()=>{
  it('clears the earlier answer and citations on typing without another request',async()=>{
    const f=vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(p.body));vi.stubGlobal('fetch',f);render(<p.Component/>);
    fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByText(p.text);expect(screen.getByText('Fictional source passage.')).toBeVisible();
    fireEvent.change(screen.getByLabelText(p.label),{target:{value:'A different fictional question'}});
    expect(screen.queryByText(p.text)).toBeNull();expect(screen.queryByText('Fictional source passage.')).toBeNull();expect(screen.getByText(p.notice)).toBeVisible();expect(f).toHaveBeenCalledTimes(2);
  });
  it('example selection clears the old draft without automatically submitting',async()=>{
    const f=vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(p.body));vi.stubGlobal('fetch',f);render(<p.Component/>);fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByText(p.text);
    fireEvent.click(screen.getByRole('button',{name:p.name==='knowledge'?'Viewing example':'Complaint example'}));expect(screen.queryByText(p.text)).toBeNull();expect(screen.getByText(p.notice)).toBeVisible();expect(f).toHaveBeenCalledTimes(2);
  });
  it('clears an old failure on edit without retrying automatically',async()=>{
    const f=vi.fn().mockRejectedValue(new Error('failure'));vi.stubGlobal('fetch',f);render(<p.Component/>);fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByRole('alert');fireEvent.change(screen.getByLabelText(p.label),{target:{value:'Updated fictional enquiry'}});expect(screen.queryByRole('alert')).toBeNull();expect(f).toHaveBeenCalledTimes(1);
  });
  it('only displays a new answer after an explicit submission of edited text',async()=>{
    const f=vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(p.body)).mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(p.body));vi.stubGlobal('fetch',f);render(<p.Component/>);fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByText(p.text);
    fireEvent.change(screen.getByLabelText(p.label),{target:{value:'Updated fictional enquiry'}});fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByText(p.text);expect(screen.queryByText(p.notice)).toBeNull();expect(f).toHaveBeenCalledTimes(4);expect(JSON.parse(f.mock.calls[3][1].body)).toEqual({[p.key]:'Updated fictional enquiry'});
  });
});
