import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AgentCard } from '@/features/agents/AgentCard';
import { agentDemoLink } from '@/services/agentDemoLinks';
import type { AgentDescriptor } from '@/types/api';

const agent=(id='qualification'):AgentDescriptor=>({agent_id:id,name:'Fictional Test Agent',description:'Registry description',responsibilities:['Test responsibility'],implementation_status:'functional',allowed_tools:['analytics.score_lead'],timeout_seconds:20,version:'1.0'});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('agent demo navigation',()=>{
  it('maps each supported agent to its existing demo page',()=>{for(const [id,href] of [['lead_intake','/leads'],['qualification','/workflows'],['property_recommendation','/properties'],['sales_conversation','/conversations'],['documents','/knowledge']])expect(agentDemoLink(agent(id))?.href).toBe(href);});
  it('uses only fixed local paths without data or credentials',()=>{for(const id of ['lead_intake','qualification','property_recommendation','sales_conversation','documents']){const demo=agentDemoLink(agent(id))!;expect(demo.href).toMatch(/^\/[a-z]+$/);expect(demo.label).toContain('fictional');expect(demo.description).toBeTruthy();}});
  it('offers no demo for unsupported or arbitrary identifiers',()=>{for(const id of ['voice','crm','email','whatsapp','supervisor','constructor','https://example.test'])expect(agentDemoLink(agent(id))).toBeNull();});
  it('does not offer a demo for an interface-only agent',()=>{expect(agentDemoLink({...agent(),implementation_status:'interface_only'})).toBeNull();});
  it('renders the qualification link with score explanation guidance',()=>{render(<AgentCard agent={agent()}/>);expect(screen.getByRole('link',{name:'Open fictional qualification demo'})).toHaveAttribute('href','/workflows');expect(screen.getByText(/inspect its score rules/)).toBeVisible();});
  it('allows a supported partial agent to open its unsent draft panel',()=>{render(<AgentCard agent={{...agent('sales_conversation'),implementation_status:'partial'}}/>);expect(screen.getByRole('link',{name:'Open fictional reply demo'})).toHaveAttribute('href','/conversations');expect(screen.getByText(/unsent reply draft/)).toBeVisible();});
  it('preserves registry tool permissions and status without invoking them',()=>{const f=vi.fn();vi.stubGlobal('fetch',f);const value=agent();const before=JSON.stringify(value);render(<AgentCard agent={value}/>);expect(screen.getByText('analytics.score_lead')).toBeVisible();expect(screen.getByText('Test responsibility')).toBeVisible();expect(JSON.stringify(value)).toBe(before);expect(f).not.toHaveBeenCalled();});
  it('does not invent actions or links for the voice interface',()=>{render(<AgentCard agent={{...agent('voice'),implementation_status:'interface_only',allowed_tools:[]}}/>);expect(screen.queryByRole('link')).toBeNull();expect(screen.getByText('No tools granted.')).toBeVisible();expect(screen.queryByRole('button')).toBeNull();});
});
