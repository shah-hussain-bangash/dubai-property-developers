import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { validateProspect, duplicateProspect, parseWorkspace, emptyWorkspace } from '@/services/prospectResearch';
import { parseProspectCsv } from '@/services/prospectCsv';
import { ProspectResearchWorkspace } from '@/features/prospects/ProspectResearchWorkspace';
import { accessProspectDatabase } from '@/services/prospectDatabase';
vi.mock('@/services/prospectDatabase',()=>({accessProspectDatabase:vi.fn()}));
const input={name:'Fictional Person',company:'Fictional Co',role:'Director',country:'UAE',email:'person@example.com',phone:'+971501234567',source:'https://example.com/team',relevance:'Fictional business role; interest unknown.'};
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('loads legacy records without inventing a WhatsApp number',()=>{
  const saved=parseWorkspace(JSON.stringify({...emptyWorkspace(),prospects:[{...input,id:'legacy',collectedAt:'2026-10-26T12:00:00Z',status:'pending'}]}));
  expect(saved.prospects[0].whatsapp).toBe('');expect(saved.prospects[0].contactResources).toEqual([]);
});
it('requires a source for a reported WhatsApp number',()=>{
  expect(()=>validateProspect({...input,whatsapp:'+971501234568'})).toThrow('source');
  expect(validateProspect({...input,whatsapp:'+971501234568',whatsappSource:'https://example.com/contact'}).whatsapp).toBe('+971501234568');
});
it('rejects unsafe resources and caps their number',()=>{
  for(const contactResources of [['javascript:alert(1)'],['https://user:secret@example.com'],Array(6).fill('https://example.com')])expect(()=>validateProspect({...input,contactResources})).toThrow();
});
it('detects duplicate numbers across phone and WhatsApp fields',()=>{
  const record={...input,id:'record',collectedAt:'2026-10-26T12:00:00Z',status:'pending' as const};
  expect(duplicateProspect([record],{...input,name:'Different',email:'other@example.com',phone:'',whatsapp:input.phone})).toBe(true);
});
it('imports optional contact columns and quoted resource lines',()=>{
  const csv='name,company,role,country,email,phone,source,relevance,whatsapp,whatsapp_source,contact_resources\nFictional Person,Fictional Co,Director,UAE,,,https://example.com/team,Public role,+971501234568,https://example.com/contact,"https://example.com/contact\nhttps://example.com/profile"';
  const result=validateProspect(parseProspectCsv(csv)[0]);expect(result.whatsappSource).toBe('https://example.com/contact');expect(result.contactResources).toHaveLength(2);
});
it('saves explicitly reported contact channels and keeps them unverified',async()=>{
  localStorage.clear();const db=vi.mocked(accessProspectDatabase);db.mockReset();db.mockImplementation(async update=>update?{revision:2,workspace:update.workspace}:{revision:1,workspace:emptyWorkspace()});
  render(<ProspectResearchWorkspace/>);await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Save prospect for review'})).toBeEnabled());
  const fields:Record<string,string>={'Full name':input.name,'Company':input.company,'Business role':input.role,'Country':input.country,'Public source URL (HTTPS)':input.source,'Evidence of relevance':input.relevance,'Reported WhatsApp number (optional, unverified)':'+971501234568','Public source for WhatsApp number':'https://example.com/contact','Other public contact resources (up to five HTTPS URLs, one per line)':'https://example.com/profile'};
  for(const [label,value] of Object.entries(fields))fireEvent.change(screen.getByLabelText(label),{target:{value}});
  fireEvent.click(screen.getByRole('button',{name:'Save prospect for review'}));await screen.findByRole('heading',{name:input.name});
  expect(db.mock.calls[1][0]!.workspace.prospects[0].whatsapp).toBe('+971501234568');expect(screen.getByText(/WhatsApp permission: unknown/)).toBeVisible();
});
