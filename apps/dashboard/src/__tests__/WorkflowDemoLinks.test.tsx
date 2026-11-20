import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowsView } from '@/features/workflows/WorkflowsView';
import { useApiResource } from '@/hooks/useApiResource';
import { workflowDemoLink } from '@/services/workflowDemoLinks';
import type { WorkflowDescriptor } from '@/types/api';

vi.mock('@/hooks/useApiResource',()=>({useApiResource:vi.fn()}));
const workflow=(id='lead_processing'):WorkflowDescriptor=>({workflow_id:id,name:id,description:'Fictional workflow definition',implementation_status:'functional',steps:['validate','review']});
const items=['lead_processing','property_recommendation','sales_conversation','knowledge_support','followup_automation','crm_sync'].map(workflow);
beforeEach(()=>{vi.mocked(useApiResource).mockReturnValue({data:{items,total:items.length},source:'live',error:null,reload:vi.fn()});});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('workflow demo shortcuts',()=>{
  it('maps supported definitions to the correct existing demo panels',()=>{for(const [id,href] of [['lead_processing','/leads'],['property_recommendation','/properties'],['sales_conversation','/conversations'],['knowledge_support','/knowledge']])expect(workflowDemoLink(workflow(id))?.href).toBe(href);});
  it('uses fixed local links without query data or credentials',()=>{for(const id of ['lead_processing','property_recommendation','sales_conversation','knowledge_support']){const demo=workflowDemoLink(workflow(id))!;expect(demo.href).toMatch(/^\/[a-z]+$/);expect(demo.label).toContain('fictional');expect(demo.description).toBeTruthy();}});
  it('does not invent demos for unsupported definitions or interface-only entries',()=>{for(const id of ['followup_automation','crm_sync','future','constructor','https://example.test'])expect(workflowDemoLink(workflow(id))).toBeNull();expect(workflowDemoLink({...workflow(),implementation_status:'interface_only'})).toBeNull();});
  it('describes supported partial workflows as unsent drafts',()=>{const demo=workflowDemoLink({...workflow('sales_conversation'),implementation_status:'partial'});expect(demo?.description).toContain('unsent');expect(demo?.href).toBe('/conversations');});
  it('renders all four demo links while preserving workflow steps',()=>{render(<WorkflowsView/>);expect(screen.getAllByRole('link',{name:/Open fictional .* workflow demo/})).toHaveLength(4);expect(screen.getByRole('link',{name:'Open fictional lead workflow demo'})).toHaveAttribute('href','/leads');expect(screen.getAllByText('validate').length).toBeGreaterThan(0);});
  it('retains links and the guided form under registry filtering',()=>{render(<WorkflowsView/>);fireEvent.change(screen.getByLabelText('Search workflows'),{target:{value:'knowledge_support'}});expect(screen.getAllByRole('link',{name:/Open fictional .* workflow demo/})).toHaveLength(1);expect(screen.getByRole('link',{name:'Open fictional knowledge workflow demo'})).toHaveAttribute('href','/knowledge');expect(screen.getByRole('button',{name:'Run guided demo'})).toBeVisible();});
  it('makes no workflow execution request merely by showing navigation links',()=>{const fetch=vi.fn();vi.stubGlobal('fetch',fetch);const before=JSON.stringify(items);render(<WorkflowsView/>);expect(JSON.stringify(items)).toBe(before);expect(fetch).not.toHaveBeenCalled();});
  it('preserves the fallback source notice and its navigation',()=>{vi.mocked(useApiResource).mockReturnValue({data:{items,total:items.length},source:'demo',error:'Unavailable',reload:vi.fn()});render(<WorkflowsView/>);expect(screen.getByText('Backend unreachable — showing demo workflows')).toBeVisible();expect(screen.getByRole('link',{name:'Open fictional property workflow demo'})).toBeVisible();});
});
