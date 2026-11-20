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
for (const p of panels) describe(p.name+' clear input and draft',()=>{
 const clearName=p.name==='knowledge'?'Clear demo question':'Clear demo message';
 it('clears the input, answer, citations and report without another request',async()=>{const f=vi.fn().mockResolvedValueOnce(response(capability)).mockResolvedValueOnce(response(p.body));vi.stubGlobal('fetch',f);render(<p.Component/>);fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByText(p.text);fireEvent.click(screen.getByRole('button',{name:clearName}));expect(screen.getByLabelText(p.label)).toHaveValue('');expect(screen.getByLabelText(p.label)).toHaveFocus();expect(screen.queryByText(p.text)).toBeNull();expect(screen.queryByText('Fictional source passage.')).toBeNull();expect(screen.queryByRole('button',{name:p.name==='knowledge'?'Download knowledge report':'Download reply report'})).toBeNull();expect(screen.getByText(/and draft cleared. Nothing was sent./)).toBeVisible();expect(f).toHaveBeenCalledTimes(2);});
 it('clears a failed attempt without retrying',async()=>{const f=vi.fn().mockRejectedValue(new Error('failed'));vi.stubGlobal('fetch',f);render(<p.Component/>);fireEvent.click(screen.getByRole('button',{name:p.button}));await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:clearName}));expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByLabelText(p.label)).toHaveFocus();expect(f).toHaveBeenCalledOnce();});
 it('disables clearing while a request is pending',()=>{vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(()=>{})));render(<p.Component/>);const input=screen.getByLabelText(p.label);const before=(input as HTMLTextAreaElement).value;fireEvent.click(screen.getByRole('button',{name:p.button}));fireEvent.click(screen.getByRole('button',{name:clearName}));expect(screen.getByRole('button',{name:clearName})).toBeDisabled();expect(input).toHaveValue(before);expect(screen.queryByText(/and draft cleared. Nothing was sent./)).toBeNull();});
 it('allows a new example after clearing without automatically submitting',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);render(<p.Component/>);fireEvent.click(screen.getByRole('button',{name:clearName}));expect(screen.getByLabelText(p.label)).toBeInvalid();fireEvent.click(screen.getByRole('button',{name:'Payment plan example'}));expect(screen.getByLabelText(p.label)).toBeValid();expect(screen.queryByText(/and draft cleared. Nothing was sent./)).toBeNull();expect(f).not.toHaveBeenCalled();});
});
