import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { accessProspectDatabase } from '@/services/prospectDatabase';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
import { validateProspect, duplicateProspect, parseWorkspace, emptyWorkspace, PROSPECT_STORAGE_KEY, type Prospect } from '@/services/prospectResearch';
const input={name:'Example Person',company:'Example Company',role:'Director',country:'UAE',email:'person@example.com',phone:'+971501234567',source:'https://example.com/team',relevance:'Listed as director on company team page; buying interest unknown.'};
const record:Prospect={...input,id:'test-id',collectedAt:'2026-10-26T10:00:00.000Z',status:'pending'};
beforeEach(()=>{localStorage.clear();vi.mocked(accessProspectDatabase).mockReset();vi.mocked(accessProspectDatabase).mockImplementation(async update=>update?{revision:update.revision+1,workspace:update.workspace}:{revision:0,workspace:emptyWorkspace()});});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it('rejects unsafe source schemes and embedded credentials',()=>{
  for(const source of ['javascript:alert(1)','http://example.com','https://user:secret@example.com']) expect(()=>validateProspect({...input,source})).toThrow();
});
it('normalises email and finds duplicate contacts even when archived',()=>{
  expect(validateProspect({...input,email:' PERSON@EXAMPLE.COM '}).email).toBe('person@example.com');
  expect(duplicateProspect([{...record,status:'archived'}],{...input,name:'Changed name'})).toBe(true);
  expect(duplicateProspect([record],{...input,email:'',phone:'',name:' example person '})).toBe(true);
});
it('does not accept malformed saved records or duplicate IDs',()=>{
  expect(()=>parseWorkspace(JSON.stringify({...emptyWorkspace(),prospects:[record,{...record,email:'other@example.com',name:'Other',phone:''}]}))).toThrow();
  expect(()=>parseWorkspace(JSON.stringify({...emptyWorkspace(),prospects:[{...record,status:'approved-to-send'}]}))).toThrow();
});
it('loads PostgreSQL and saves audience settings without writing browser storage',async()=>{
  render(<ProspectResearchWorkspace/>);await screen.findByText(/Storage: PostgreSQL/);
  await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Save audience settings'})).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Target countries'),{target:{value:'UAE, UK'}});
  fireEvent.click(screen.getByRole('button',{name:'Save audience settings'}));
  expect(await screen.findByRole('status')).toHaveTextContent('saved in PostgreSQL');
  expect(vi.mocked(accessProspectDatabase).mock.calls.at(-1)?.[0]?.workspace.target.countries).toBe('UAE, UK');
  expect(localStorage.getItem(PROSPECT_STORAGE_KEY)).toBeNull();
});
it('preserves and explicitly copies a browser backup',async()=>{
  const saved=JSON.stringify({...emptyWorkspace(),prospects:[record]});localStorage.setItem(PROSPECT_STORAGE_KEY,saved);
  render(<ProspectResearchWorkspace/>);const button=await screen.findByRole('button',{name:'Copy browser workspace to PostgreSQL'});
  await vi.waitFor(()=>expect(button).toBeEnabled());expect(accessProspectDatabase).toHaveBeenCalledTimes(1);
  fireEvent.click(button);expect(await screen.findByRole('heading',{name:input.name})).toBeVisible();
  expect(localStorage.getItem(PROSPECT_STORAGE_KEY)).toBe(saved);
});
it('fails closed when PostgreSQL cannot load',async()=>{
  vi.mocked(accessProspectDatabase).mockRejectedValue(new Error('private connection string'));
  render(<ProspectResearchWorkspace/>);expect(await screen.findByRole('alert')).not.toHaveTextContent('private connection string');
  expect(screen.getByRole('button',{name:'Save prospect for review'})).toBeDisabled();
});
it('does not change the displayed review status on revision conflict',async()=>{
  vi.mocked(accessProspectDatabase).mockResolvedValueOnce({revision:4,workspace:{...emptyWorkspace(),prospects:[record]}}).mockRejectedValueOnce(new Error('Another session changed this workspace. Reload before editing.'));
  render(<ProspectResearchWorkspace/>);await screen.findByRole('heading',{name:input.name});
  fireEvent.click(screen.getByRole('button',{name:'Mark reviewed'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Reload');
  expect(screen.getByText('Awaiting review',{selector:'span'})).toBeVisible();
  expect(screen.getByRole('button',{name:'Mark reviewed'})).toBeDisabled();
});
