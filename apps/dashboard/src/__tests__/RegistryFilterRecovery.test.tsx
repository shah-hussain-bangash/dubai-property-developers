import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AgentsView } from '@/features/agents/AgentsView';
import { WorkflowsView } from '@/features/workflows/WorkflowsView';
import { useApiResource } from '@/hooks/useApiResource';
import { DEMO_AGENTS_RESPONSE, DEMO_WORKFLOWS_RESPONSE } from '@/lib/demo-data';
vi.mock('@/hooks/useApiResource',()=>({useApiResource:vi.fn()}));
const setup=(kind:'agent'|'workflow',empty=false)=>{
 const data=kind==='agent'?DEMO_AGENTS_RESPONSE:DEMO_WORKFLOWS_RESPONSE;
 vi.mocked(useApiResource).mockReturnValue({data:empty?{items:[],total:0}:data,source:'live',error:null,reload:vi.fn()});
 render(kind==='agent'?<AgentsView/>:<WorkflowsView/>);
};
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('registry filter recovery',()=>{
 it('recovers all agents from a no-match search and returns focus',()=>{setup('agent');const input=screen.getByLabelText('Search agents');fireEvent.change(input,{target:{value:'no-such-fictional-agent'}});fireEvent.change(screen.getByLabelText('Implementation status'),{target:{value:'functional'}});fireEvent.click(screen.getByRole('button',{name:'Show all agents'}));expect(input).toHaveValue('');expect(input).toHaveFocus();expect(screen.getByLabelText('Implementation status')).toHaveValue('all');expect(screen.queryByText('No agents match these filters')).toBeNull();expect(screen.getByRole('list',{name:'Agents'})).toBeVisible();});
 it('recovers all workflow definitions and returns focus',()=>{setup('workflow');const input=screen.getByLabelText('Search workflows');fireEvent.change(input,{target:{value:'no-such-fictional-workflow'}});fireEvent.change(screen.getByLabelText('Workflow implementation status'),{target:{value:'functional'}});fireEvent.click(screen.getByRole('button',{name:'Show all workflow definitions'}));expect(input).toHaveValue('');expect(input).toHaveFocus();expect(screen.getByLabelText('Workflow implementation status')).toHaveValue('all');expect(screen.getByRole('list',{name:'Workflows'})).toBeVisible();});
 it('also restores focus through the existing agent reset control',()=>{setup('agent');const input=screen.getByLabelText('Search agents');fireEvent.change(input,{target:{value:'voice'}});fireEvent.click(screen.getByRole('button',{name:'Reset agent filters'}));expect(input).toHaveFocus();expect(input).toHaveValue('');});
 it('also restores focus through the existing workflow reset control',()=>{setup('workflow');const input=screen.getByLabelText('Search workflows');fireEvent.change(input,{target:{value:'lead'}});fireEvent.click(screen.getByRole('button',{name:'Reset workflow filters'}));expect(input).toHaveFocus();expect(input).toHaveValue('');});
 it('does not offer filter recovery for an actually empty agent registry',()=>{setup('agent',true);expect(screen.getByText('No agents registered')).toBeVisible();expect(screen.queryByRole('button',{name:'Show all agents'})).toBeNull();});
 it('does not offer filter recovery for an actually empty workflow registry',()=>{setup('workflow',true);expect(screen.getByText('No workflows registered')).toBeVisible();expect(screen.queryByRole('button',{name:'Show all workflow definitions'})).toBeNull();});
 it('agent recovery makes no request and leaves no-match actions absent afterwards',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);setup('agent');fireEvent.change(screen.getByLabelText('Search agents'),{target:{value:'no-such-agent'}});fireEvent.click(screen.getByRole('button',{name:'Show all agents'}));expect(f).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'Show all agents'})).toBeNull();});
 it('workflow recovery keeps the guided demo available without submitting it',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);setup('workflow');fireEvent.change(screen.getByLabelText('Search workflows'),{target:{value:'no-such-workflow'}});expect(screen.getByRole('button',{name:'Run guided demo'})).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Show all workflow definitions'}));expect(screen.getByRole('button',{name:'Run guided demo'})).toBeVisible();expect(f).not.toHaveBeenCalled();});
});
