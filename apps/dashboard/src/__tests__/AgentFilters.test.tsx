import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentsView } from '@/features/agents/AgentsView';
import { useApiResource } from '@/hooks/useApiResource';
import { filterAgents } from '@/services/agentFilters';
import type { AgentDescriptor } from '@/types/api';

vi.mock('@/hooks/useApiResource',()=>({useApiResource:vi.fn()}));
const agents:AgentDescriptor[]=[
  {agent_id:'qualification',name:'Lead Qualification Agent',description:'Scores enquiries',responsibilities:['Assess readiness'],implementation_status:'functional',allowed_tools:['analytics.score_lead'],timeout_seconds:30,version:'1.0'},
  {agent_id:'sales_conversation',name:'Sales Conversation Agent',description:'Prepares draft replies',responsibilities:['Handle complaints'],implementation_status:'partial',allowed_tools:['knowledge.retrieve'],timeout_seconds:30,version:'1.0'},
  {agent_id:'voice',name:'Voice Agent',description:'Planned call interface',responsibilities:['Voice conversations'],implementation_status:'interface_only',allowed_tools:[],timeout_seconds:30,version:'1.0'},
];
beforeEach(()=>{vi.mocked(useApiResource).mockReturnValue({data:{items:agents,total:3},source:'live',error:null,reload:vi.fn()});});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('agent registry filters',()=>{
  it('searches names and identifiers without case or outer whitespace sensitivity',()=>{expect(filterAgents(agents,'  QUALIFICATION  ','all').map(a=>a.agent_id)).toEqual(['qualification']);});
  it('searches descriptions, responsibilities and permitted tool names',()=>{for(const term of ['draft replies','complaints','knowledge.retrieve'])expect(filterAgents(agents,term,'all').map(a=>a.agent_id)).toEqual(['sales_conversation']);});
  it('filters each implementation status exactly',()=>{for(const status of ['functional','partial','interface_only'] as const)expect(filterAgents(agents,'',status).every(a=>a.implementation_status===status)).toBe(true);expect(filterAgents(agents,'','interface_only')).toHaveLength(1);});
  it('combines search with implementation status',()=>{expect(filterAgents(agents,'analytics.score','functional')).toHaveLength(1);expect(filterAgents(agents,'analytics.score','partial')).toEqual([]);});
  it('does not mutate registry metadata and handles empty inputs',()=>{const before=JSON.stringify(agents);expect(filterAgents(agents,'   ','all')).toHaveLength(3);expect(filterAgents([],'','all')).toEqual([]);expect(JSON.stringify(agents)).toBe(before);});
  it('shows local filter controls and exact visible counts',()=>{render(<AgentsView/>);expect(screen.getByLabelText('Search agents')).toBeVisible();expect(screen.getByText('3 of 3 agents shown')).toBeVisible();expect(screen.getByRole('button',{name:'Reset agent filters'})).toBeDisabled();});
  it('filters cards locally without a fetch or tool execution',()=>{const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<AgentsView/>);fireEvent.change(screen.getByLabelText('Search agents'),{target:{value:'knowledge.retrieve'}});expect(screen.getByText('1 of 3 agents shown')).toBeVisible();expect(screen.queryByRole('heading',{name:'Voice Agent'})).toBeNull();expect(screen.getByRole('heading',{name:'Sales Conversation Agent'})).toBeVisible();expect(fetch).not.toHaveBeenCalled();});
  it('shows a clear no-match state and resets both filters',()=>{render(<AgentsView/>);fireEvent.change(screen.getByLabelText('Implementation status'),{target:{value:'functional'}});fireEvent.change(screen.getByLabelText('Search agents'),{target:{value:'voice'}});expect(screen.getByText('No agents match these filters')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Reset agent filters'}));expect(screen.getByText('3 of 3 agents shown')).toBeVisible();expect(screen.getByLabelText('Implementation status')).toHaveValue('all');expect(screen.getByLabelText('Search agents')).toHaveValue('');});
  it('preserves the demo fallback warning while filtering',()=>{vi.mocked(useApiResource).mockReturnValue({data:{items:agents,total:3},source:'demo',error:'Unavailable',reload:vi.fn()});render(<AgentsView/>);fireEvent.change(screen.getByLabelText('Implementation status'),{target:{value:'interface_only'}});expect(screen.getByText('Backend unreachable — showing demo agents')).toBeVisible();expect(screen.getByRole('heading',{name:'Voice Agent'})).toBeVisible();expect(screen.getByText(/not confirm that live integrations/)).toBeVisible();});
  it('keeps the empty registry state distinct from an unmatched search',()=>{vi.mocked(useApiResource).mockReturnValue({data:{items:[],total:0},source:'live',error:null,reload:vi.fn()});render(<AgentsView/>);expect(screen.getByText('No agents registered')).toBeVisible();expect(screen.queryByText('No agents match these filters')).toBeNull();expect(screen.getByText('0 of 0 agents shown')).toBeVisible();});
});
