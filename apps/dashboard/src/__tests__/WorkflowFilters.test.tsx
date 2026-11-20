import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowsView } from '@/features/workflows/WorkflowsView';
import { useApiResource } from '@/hooks/useApiResource';
import { filterWorkflows } from '@/services/workflowFilters';
import type { WorkflowDescriptor } from '@/types/api';

vi.mock('@/hooks/useApiResource',()=>({useApiResource:vi.fn()}));
const items:WorkflowDescriptor[]=[
  {workflow_id:'lead_processing',name:'Lead Processing',description:'Qualifies inbound enquiries',implementation_status:'functional',steps:['validate_normalize_deduplicate','store_in_crm']},
  {workflow_id:'sales_conversation',name:'Sales Conversation',description:'Drafts replies or hands off to staff',implementation_status:'partial',steps:['detect_intent','approve_and_dispatch']},
  {workflow_id:'future_demo',name:'Future Interface',description:'Planned workflow',implementation_status:'interface_only',steps:[]},
];
beforeEach(()=>{vi.mocked(useApiResource).mockReturnValue({data:{items,total:3},source:'live',error:null,reload:vi.fn()});});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('workflow registry filters',()=>{
  it('matches names and identifiers with trimmed case-insensitive queries',()=>{expect(filterWorkflows(items,'  LEAD_PROCESSING  ','all').map(w=>w.workflow_id)).toEqual(['lead_processing']);expect(filterWorkflows(items,'Sales Conversation','all')).toHaveLength(1);});
  it('matches descriptions and raw or readable step names',()=>{for(const term of ['inbound enquiries','store_in_crm','store in crm'])expect(filterWorkflows(items,term,'all').map(w=>w.workflow_id)).toEqual(['lead_processing']);});
  it('combines implementation status with search',()=>{expect(filterWorkflows(items,'dispatch','partial')).toHaveLength(1);expect(filterWorkflows(items,'dispatch','functional')).toEqual([]);expect(filterWorkflows(items,'','interface_only')).toHaveLength(1);});
  it('preserves definitions and step ordering and handles blank queries',()=>{const before=JSON.stringify(items);expect(filterWorkflows(items,'   ','all')).toHaveLength(3);expect(filterWorkflows([],'','all')).toEqual([]);expect(JSON.stringify(items)).toBe(before);});
  it('filters registry cards without requests and leaves the guided demo available',()=>{const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<WorkflowsView/>);fireEvent.change(screen.getByLabelText('Search workflows'),{target:{value:'approve and dispatch'}});expect(screen.getByText('1 of 3 workflow definitions shown')).toBeVisible();expect(screen.getByRole('heading',{name:'Sales Conversation'})).toBeVisible();expect(screen.queryByRole('heading',{name:'Lead Processing'})).toBeNull();expect(screen.getByRole('button',{name:'Run guided demo'})).toBeVisible();expect(fetch).not.toHaveBeenCalled();});
  it('shows a no-match state and resets both filters',()=>{render(<WorkflowsView/>);fireEvent.change(screen.getByLabelText('Workflow implementation status'),{target:{value:'functional'}});fireEvent.change(screen.getByLabelText('Search workflows'),{target:{value:'dispatch'}});expect(screen.getByText('No workflow definitions match')).toBeVisible();expect(screen.getByRole('button',{name:'Run guided demo'})).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Reset workflow filters'}));expect(screen.getByText('3 of 3 workflow definitions shown')).toBeVisible();expect(screen.getByLabelText('Workflow implementation status')).toHaveValue('all');});
  it('retains the fallback warning while filtering copied definitions',()=>{vi.mocked(useApiResource).mockReturnValue({data:{items,total:3},source:'demo',error:'Unavailable',reload:vi.fn()});render(<WorkflowsView/>);fireEvent.change(screen.getByLabelText('Workflow implementation status'),{target:{value:'partial'}});expect(screen.getByText('Backend unreachable — showing demo workflows')).toBeVisible();expect(screen.getByText(/These workflow definitions are a local copy/)).toBeVisible();expect(screen.getByText('1 of 3 workflow definitions shown')).toBeVisible();});
  it('keeps an empty registry distinct from filters with no matches',()=>{vi.mocked(useApiResource).mockReturnValue({data:{items:[],total:0},source:'live',error:null,reload:vi.fn()});render(<WorkflowsView/>);expect(screen.getByText('No workflows registered')).toBeVisible();expect(screen.queryByText('No workflow definitions match')).toBeNull();expect(screen.getByText('0 of 0 workflow definitions shown')).toBeVisible();expect(screen.getByRole('button',{name:'Reset workflow filters'})).toBeDisabled();});
});
